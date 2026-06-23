import frappe
from frappe.utils import getdate, now_datetime

from receivable_risk_manager.services.risk_scoring import calculate_invoice_risk


INVOICE_DOCTYPE = "Receivables Invoice"
CUSTOMER_DOCTYPE = "Receivables Customer"
ASSESSMENT_DOCTYPE = "Invoice Risk Assessment"
BATCH_SIZE = 500


def get_analysis_date():
	"""Return the latest posting date from Receivables Invoice.

	The source dataset is historical, so this date is used instead of today's
	date when calculating overdue days.
	"""

	result = frappe.db.sql(
		f"""
		SELECT MAX(posting_date) AS analysis_date
		FROM `tab{INVOICE_DOCTYPE}`
		WHERE posting_date IS NOT NULL
		""",
		as_dict=True,
	)

	analysis_date = result[0].analysis_date if result else None
	if not analysis_date:
		frappe.throw("Cannot calculate invoice risk because no Receivables Invoice posting_date was found.")

	return getdate(analysis_date)


def build_invoice_metrics(invoice_doc, customer_doc, analysis_date):
	"""Build the metrics dictionary expected by calculate_invoice_risk()."""

	due_date = getdate(invoice_doc.due_date) if invoice_doc.due_date else None
	analysis_date = getdate(analysis_date)

	if due_date:
		days_overdue = max((analysis_date - due_date).days, 0)
	else:
		days_overdue = 0

	total_invoice_amount = customer_doc.total_invoice_amount or 0
	total_invoices = customer_doc.total_invoices or 0
	average_invoice_amount = total_invoice_amount / total_invoices if total_invoices else 0

	return {
		"days_overdue": days_overdue,
		"invoice_amount": invoice_doc.invoice_amount or 0,
		"average_invoice_amount": average_invoice_amount,
		"customer_risk_level": customer_doc.risk_level or "Low",
	}


def recalculate_invoice_risk_assessment(invoice_name, analysis_date=None):
	"""Create or update risk assessment for one open Receivables Invoice."""

	analysis_date = getdate(analysis_date) if analysis_date else get_analysis_date()
	invoice_doc = frappe.get_doc(INVOICE_DOCTYPE, invoice_name)

	if not invoice_doc.is_open:
		assessment_name = (
			frappe.db.exists(ASSESSMENT_DOCTYPE, {"external_invoice_id": invoice_doc.invoice_id})
			or frappe.db.exists(ASSESSMENT_DOCTYPE, {"receivables_invoice": invoice_doc.name})
		)
		if assessment_name:
			_mark_assessment_as_closed(assessment_name, invoice_doc)

		return {
			"invoice": invoice_doc.name,
			"status": "skipped",
			"reason": "Invoice is closed.",
		}

	customer_name = frappe.db.exists(CUSTOMER_DOCTYPE, {"customer_id": invoice_doc.customer_id})
	if not customer_name:
		frappe.throw(
			f"Receivables Customer is missing for customer_id {invoice_doc.customer_id} "
			f"on invoice {invoice_doc.name}."
		)

	customer_doc = frappe.get_doc(CUSTOMER_DOCTYPE, customer_name)
	metrics = build_invoice_metrics(invoice_doc, customer_doc, analysis_date)
	risk = calculate_invoice_risk(metrics)

	assessment_name = (
		frappe.db.exists(ASSESSMENT_DOCTYPE, {"external_invoice_id": invoice_doc.invoice_id})
		or frappe.db.exists(ASSESSMENT_DOCTYPE, {"receivables_invoice": invoice_doc.name})
	)

	if assessment_name:
		assessment_doc = frappe.get_doc(ASSESSMENT_DOCTYPE, assessment_name)
		created = False
	else:
		assessment_doc = frappe.new_doc(ASSESSMENT_DOCTYPE)
		created = True

	assessment_doc.update(
		{
			"receivables_invoice": invoice_doc.name,
			"external_invoice_id": invoice_doc.invoice_id,
			"invoice_id": invoice_doc.invoice_id,
			"receivables_customer": customer_doc.name,
			"customer_id": invoice_doc.customer_id,
			"customer_name": customer_doc.customer_name,
			"posting_date": invoice_doc.posting_date,
			"due_date": invoice_doc.due_date,
			"currency": invoice_doc.currency,
			"invoice_amount": invoice_doc.invoice_amount,
			"is_open": invoice_doc.is_open,
			"days_overdue": metrics["days_overdue"],
			"customer_risk_score": customer_doc.risk_score or 0,
			"customer_risk_level": customer_doc.risk_level or "Low",
			"risk_score": risk["risk_score"],
			"risk_level": risk["risk_level"],
			"suggested_action": risk["suggested_action"],
			"explanation": risk["explanation"],
			"last_calculated_on": now_datetime(),
		}
	)
	assessment_doc.save(ignore_permissions=True)

	return {
		"invoice": invoice_doc.name,
		"assessment": assessment_doc.name,
		"status": "created" if created else "updated",
		"risk_score": assessment_doc.risk_score,
		"risk_level": assessment_doc.risk_level,
	}


def mark_closed_invoice_assessments():
	"""Mark risk assessments as closed when the linked invoice is no longer open."""

	summary = {
		"closed_assessments_found": 0,
		"closed_assessments_updated": 0,
		"errors": [],
	}

	closed_assessments = frappe.db.sql(
		f"""
		SELECT
			assessment.name AS assessment_name,
			invoice.name AS invoice_name
		FROM `tab{ASSESSMENT_DOCTYPE}` assessment
		INNER JOIN `tab{INVOICE_DOCTYPE}` invoice
			ON invoice.name = assessment.receivables_invoice
		WHERE IFNULL(invoice.is_open, 0) = 0
		  AND IFNULL(assessment.is_open, 0) != 0
		ORDER BY assessment.name
		""",
		as_dict=True,
	)

	for row in closed_assessments:
		summary["closed_assessments_found"] += 1

		try:
			invoice_doc = frappe.get_doc(INVOICE_DOCTYPE, row.invoice_name)
			_mark_assessment_as_closed(row.assessment_name, invoice_doc)
			summary["closed_assessments_updated"] += 1

			if summary["closed_assessments_updated"] % BATCH_SIZE == 0:
				frappe.db.commit()

		except Exception:
			error = {
				"assessment": row.assessment_name,
				"invoice": row.invoice_name,
				"error": frappe.get_traceback(),
			}
			summary["errors"].append(error)
			frappe.log_error(
				title=f"Closed invoice assessment cleanup failed: {row.assessment_name}",
				message=error["error"],
			)

	frappe.db.commit()
	return summary


def _mark_assessment_as_closed(assessment_name, invoice_doc):
	assessment_doc = frappe.get_doc(ASSESSMENT_DOCTYPE, assessment_name)
	assessment_doc.update(
		{
			"is_open": 0,
			"risk_score": 0,
			"risk_level": "Low",
			"suggested_action": "No action - invoice closed",
			"explanation": (
				f"Linked Receivables Invoice {invoice_doc.name} is closed. "
				"No collection action is required."
			),
			"last_calculated_on": now_datetime(),
		}
	)
	assessment_doc.save(ignore_permissions=True)


def recalculate_all_invoice_risk_assessments(analysis_date=None):
	"""Recalculate risk assessments for all open Receivables Invoice records."""

	analysis_date = getdate(analysis_date) if analysis_date else get_analysis_date()
	summary = {
		"analysis_date": str(analysis_date),
		"open_invoices_processed": 0,
		"assessments_created": 0,
		"assessments_updated": 0,
		"skipped": 0,
		"closed_assessment_cleanup": None,
		"errors": [],
	}

	open_invoices = frappe.get_all(
		INVOICE_DOCTYPE,
		filters={"is_open": 1},
		fields=["name"],
		order_by="name asc",
	)

	for row in open_invoices:
		invoice_name = row.name
		summary["open_invoices_processed"] += 1

		try:
			result = recalculate_invoice_risk_assessment(invoice_name, analysis_date=analysis_date)
			if result["status"] == "created":
				summary["assessments_created"] += 1
			elif result["status"] == "updated":
				summary["assessments_updated"] += 1
			else:
				summary["skipped"] += 1

			if summary["open_invoices_processed"] % BATCH_SIZE == 0:
				frappe.db.commit()

		except Exception:
			error = {
				"invoice": invoice_name,
				"error": frappe.get_traceback(),
			}
			summary["errors"].append(error)
			frappe.log_error(
				title=f"Invoice risk assessment failed: {invoice_name}",
				message=error["error"],
			)

	frappe.db.commit()
	summary["closed_assessment_cleanup"] = mark_closed_invoice_assessments()
	return summary

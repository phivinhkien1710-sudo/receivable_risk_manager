import frappe
from frappe.utils import now_datetime

from receivable_risk_manager.services.risk_audit import log_risk_change
from receivable_risk_manager.services.risk_scoring import calculate_customer_risk
from receivable_risk_manager.services.risk_settings import get_scoring_settings


CUSTOMER_DOCTYPE = "Receivables Customer"


def build_customer_metrics(customer_doc):
	"""Build the metrics dictionary expected by calculate_customer_risk()."""

	return {
		"total_invoices": customer_doc.get("total_invoices") or 0,
		"closed_invoice_count": customer_doc.get("closed_invoice_count") or 0,
		"open_invoice_count": customer_doc.get("open_invoice_count") or 0,
		"total_invoice_amount": customer_doc.get("total_invoice_amount") or 0,
		"open_amount": customer_doc.get("open_amount") or 0,
		"average_payment_delay": customer_doc.get("average_payment_delay") or 0,
		"late_payment_rate": customer_doc.get("late_payment_rate") or 0,
	}


def recalculate_customer_risk(customer_name):
	"""Recalculate risk fields for one Receivables Customer."""

	customer_doc = frappe.get_doc(CUSTOMER_DOCTYPE, customer_name)
	metrics = build_customer_metrics(customer_doc)
	settings = get_scoring_settings()
	risk = calculate_customer_risk(metrics, settings=settings)
	previous_score = customer_doc.risk_score
	previous_level = customer_doc.risk_level

	customer_doc.risk_score = risk["risk_score"]
	customer_doc.risk_level = risk["risk_level"]
	customer_doc.risk_explanation = risk["risk_explanation"]
	if frappe.get_meta(CUSTOMER_DOCTYPE).has_field("risk_confidence"):
		customer_doc.risk_confidence = risk.get("risk_confidence") or "Medium"
	customer_doc.risk_last_calculated_on = now_datetime()
	customer_doc.save(ignore_permissions=True)

	log_risk_change(
		reference_doctype=CUSTOMER_DOCTYPE,
		reference_name=customer_doc.name,
		entity_type="Customer",
		previous_score=previous_score,
		new_score=customer_doc.risk_score,
		previous_level=previous_level,
		new_level=customer_doc.risk_level,
		reason=customer_doc.risk_explanation,
		source="Customer Risk",
		customer_id=customer_doc.customer_id,
	)

	return {
		"customer": customer_doc.name,
		"risk_score": customer_doc.risk_score,
		"risk_level": customer_doc.risk_level,
		"risk_confidence": risk.get("risk_confidence") or "Medium",
	}


def recalculate_all_customer_risks():
	"""Recalculate risk fields for all Receivables Customer records."""

	summary = {
		"customers_processed": 0,
		"customers_updated": 0,
		"errors": [],
	}

	customers = frappe.get_all(CUSTOMER_DOCTYPE, fields=["name"], order_by="name asc")

	for customer in customers:
		customer_name = customer.name
		summary["customers_processed"] += 1

		try:
			recalculate_customer_risk(customer_name)
			summary["customers_updated"] += 1

		except Exception:
			error = {
				"customer": customer_name,
				"error": frappe.get_traceback(),
			}
			summary["errors"].append(error)
			frappe.log_error(
				title=f"Customer risk recalculation failed: {customer_name}",
				message=error["error"],
			)

	frappe.db.commit()
	return summary

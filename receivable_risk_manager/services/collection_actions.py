import frappe
from frappe.utils import add_days, getdate, now_datetime


INVOICE_DOCTYPE = "Receivables Invoice"
ASSESSMENT_DOCTYPE = "Invoice Risk Assessment"
ACTION_DOCTYPE = "Collection Action"
BATCH_SIZE = 500


def get_analysis_date():
	"""Return the latest posting date from Receivables Invoice."""

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
		frappe.throw("Cannot generate collection actions because no Receivables Invoice posting_date was found.")

	return getdate(analysis_date)


def get_action_from_assessment(assessment_doc, analysis_date):
	"""Return action details for an assessment, or None for low-risk invoices."""

	analysis_date = getdate(analysis_date)
	days_overdue = assessment_doc.days_overdue or 0
	risk_level = assessment_doc.risk_level

	if risk_level == "High" and days_overdue > 30:
		return {
			"action_type": "Escalate Collection",
			"priority": "High",
			"due_date": analysis_date,
			"notes": (
				f"High-risk invoice {assessment_doc.external_invoice_id} is {days_overdue} days overdue. "
				"Escalate collection immediately."
			),
		}

	if risk_level == "High":
		return {
			"action_type": "Immediate Follow-up",
			"priority": "High",
			"due_date": analysis_date,
			"notes": (
				f"High-risk invoice {assessment_doc.external_invoice_id} requires immediate follow-up."
			),
		}

	if risk_level == "Medium":
		return {
			"action_type": "Send Reminder",
			"priority": "Medium",
			"due_date": add_days(analysis_date, 3),
			"notes": (
				f"Medium-risk invoice {assessment_doc.external_invoice_id}. Send payment reminder."
			),
		}

	return None


def collection_action_exists(external_invoice_id, action_type):
	"""Return True if a matching Collection Action already exists.

	For the MVP, Collection Actions are unique forever by
	external_invoice_id + action_type, even if the existing action is Resolved.
	This matches the unique active_invoice_key field on the DocType.
	"""

	if not external_invoice_id or not action_type:
		return False

	active_invoice_key = get_active_invoice_key(external_invoice_id, action_type)

	if frappe.db.exists(ACTION_DOCTYPE, {"active_invoice_key": active_invoice_key}):
		return True

	return bool(
		frappe.db.exists(
			ACTION_DOCTYPE,
			{
				"external_invoice_id": external_invoice_id,
				"action_type": action_type,
			},
		)
	)


def get_active_invoice_key(external_invoice_id, action_type):
	"""Return the unique key used to prevent duplicate Collection Actions."""

	return f"{external_invoice_id}:{action_type}"


def get_collection_action_skip_type(result):
	"""Return a stable skip category for summary counts."""

	reason = result.get("reason")

	if reason == "Collection action already exists for this invoice and action type.":
		return "existing"

	return "no_action_required"


def generate_collection_action_for_assessment(assessment_name, analysis_date=None):
	"""Generate one Collection Action from one Invoice Risk Assessment."""

	analysis_date = getdate(analysis_date) if analysis_date else get_analysis_date()
	assessment_doc = frappe.get_doc(ASSESSMENT_DOCTYPE, assessment_name)
	action = get_action_from_assessment(assessment_doc, analysis_date)

	if not action:
		return {
			"assessment": assessment_doc.name,
			"status": "skipped",
			"reason": "No action required for low-risk assessment.",
		}

	if collection_action_exists(assessment_doc.external_invoice_id, action["action_type"]):
		return {
			"assessment": assessment_doc.name,
			"status": "skipped",
			"reason": "Collection action already exists for this invoice and action type.",
		}

	doc = frappe.new_doc(ACTION_DOCTYPE)
	doc.update(
		{
			"receivables_customer": assessment_doc.receivables_customer,
			"receivables_invoice": assessment_doc.receivables_invoice,
			"invoice_risk_assessment": assessment_doc.name,
			"external_invoice_id": assessment_doc.external_invoice_id,
			"customer_id": assessment_doc.customer_id,
			"customer_name": assessment_doc.customer_name,
			"action_type": action["action_type"],
			"priority": action["priority"],
			"status": "Open",
			"due_date": action["due_date"],
			"notes": action["notes"],
			"auto_generated": 1,
			"active_invoice_key": get_active_invoice_key(
				assessment_doc.external_invoice_id,
				action["action_type"],
			),
			"created_from_risk_score": assessment_doc.risk_score or 0,
			"last_updated_on": now_datetime(),
		}
	)
	doc.save(ignore_permissions=True)

	return {
		"assessment": assessment_doc.name,
		"collection_action": doc.name,
		"status": "created",
		"action_type": doc.action_type,
		"priority": doc.priority,
	}


def generate_collection_actions(analysis_date=None):
	"""Generate Collection Actions for Medium and High invoice risk assessments."""

	analysis_date = getdate(analysis_date) if analysis_date else get_analysis_date()
	summary = {
		"analysis_date": str(analysis_date),
		"closed_invoice_actions_resolved": None,
		"assessments_processed": 0,
		"actions_created": 0,
		"actions_skipped": 0,
		"actions_skipped_existing": 0,
		"actions_skipped_no_action_required": 0,
		"errors": [],
	}

	summary["closed_invoice_actions_resolved"] = resolve_actions_for_closed_invoices()

	assessments = frappe.get_all(
		ASSESSMENT_DOCTYPE,
		filters={
			"risk_level": ["in", ["Medium", "High"]],
			"is_open": 1,
		},
		fields=["name"],
		order_by="risk_score desc, days_overdue desc, name asc",
	)

	for row in assessments:
		assessment_name = row.name
		summary["assessments_processed"] += 1

		try:
			result = generate_collection_action_for_assessment(
				assessment_name,
				analysis_date=analysis_date,
			)

			if result["status"] == "created":
				summary["actions_created"] += 1
			else:
				summary["actions_skipped"] += 1
				skip_type = get_collection_action_skip_type(result)
				if skip_type == "existing":
					summary["actions_skipped_existing"] += 1
				else:
					summary["actions_skipped_no_action_required"] += 1

			if summary["actions_created"] and summary["actions_created"] % BATCH_SIZE == 0:
				frappe.db.commit()

		except Exception:
			error = {
				"assessment": assessment_name,
				"error": frappe.get_traceback(),
			}
			summary["errors"].append(error)
			frappe.log_error(
				title=f"Collection Action generation failed: {assessment_name}",
				message=error["error"],
			)

	frappe.db.commit()
	return summary


def resolve_actions_for_closed_invoices():
	"""Resolve open Collection Actions whose linked assessment is now closed."""

	summary = {
		"actions_found": 0,
		"actions_resolved": 0,
		"errors": [],
	}

	actions = frappe.db.sql(
		f"""
		SELECT
			action.name AS action_name,
			action.notes AS notes,
			assessment.name AS assessment_name,
			assessment.external_invoice_id AS external_invoice_id
		FROM `tab{ACTION_DOCTYPE}` action
		INNER JOIN `tab{ASSESSMENT_DOCTYPE}` assessment
			ON assessment.name = action.invoice_risk_assessment
		WHERE action.status != 'Resolved'
		  AND IFNULL(assessment.is_open, 0) = 0
		ORDER BY action.name
		""",
		as_dict=True,
	)

	for row in actions:
		summary["actions_found"] += 1

		try:
			closed_note = (
				f"Auto-resolved because linked Invoice Risk Assessment {row.assessment_name} "
				f"for invoice {row.external_invoice_id} is closed."
			)
			notes = row.notes or ""
			if notes:
				notes = f"{notes}\n\n{closed_note}"
			else:
				notes = closed_note

			frappe.db.set_value(
				ACTION_DOCTYPE,
				row.action_name,
				{
					"status": "Resolved",
					"notes": notes,
					"last_updated_on": now_datetime(),
				},
				update_modified=True,
			)
			summary["actions_resolved"] += 1

			if summary["actions_resolved"] % BATCH_SIZE == 0:
				frappe.db.commit()

		except Exception:
			error = {
				"collection_action": row.action_name,
				"assessment": row.assessment_name,
				"error": frappe.get_traceback(),
			}
			summary["errors"].append(error)
			frappe.log_error(
				title=f"Closed invoice action cleanup failed: {row.action_name}",
				message=error["error"],
			)

	frappe.db.commit()
	return summary

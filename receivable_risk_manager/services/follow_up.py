import frappe
from frappe.utils import date_diff, getdate, now_datetime

from receivable_risk_manager.services.collection_actions import (
	ACTION_DOCTYPE,
	ASSESSMENT_DOCTYPE,
	collection_action_exists,
	get_active_invoice_key,
	get_analysis_date,
)
from receivable_risk_manager.services.risk_audit import log_collection_action_event


ESCALATION_ACTION_TYPE = "Escalate Collection"
ESCALATION_PRIORITY = "High"
RISK_SETTINGS_DOCTYPE = "Risk Settings"
BATCH_SIZE = 500


def get_follow_up_days():
	"""Read Risk Settings.follow_up_days with a safe fallback of 3 days."""

	risk_settings = frappe.get_single(RISK_SETTINGS_DOCTYPE)
	return _safe_positive_int(risk_settings.follow_up_days, default=3)


def get_stale_collection_actions(analysis_date, follow_up_days):
	"""Return Open/Contacted Collection Actions, on invoices still open, whose
	due_date is at least follow_up_days in the past. "Promised to Pay" is
	deliberately excluded - the customer already engaged, this isn't silence.
	"""

	analysis_date = getdate(analysis_date)

	return frappe.db.sql(
		f"""
		SELECT
			action.name AS action_name,
			action.receivables_customer AS receivables_customer,
			action.receivables_invoice AS receivables_invoice,
			action.invoice_risk_assessment AS invoice_risk_assessment,
			action.external_invoice_id AS external_invoice_id,
			action.customer_id AS customer_id,
			action.customer_name AS customer_name,
			action.action_type AS action_type,
			action.due_date AS due_date,
			assessment.risk_score AS risk_score
		FROM `tab{ACTION_DOCTYPE}` action
		INNER JOIN `tab{ASSESSMENT_DOCTYPE}` assessment
			ON assessment.name = action.invoice_risk_assessment
		WHERE action.status IN ('Open', 'Contacted')
		  AND action.due_date IS NOT NULL
		  AND DATEDIFF(%(analysis_date)s, action.due_date) >= %(follow_up_days)s
		  AND IFNULL(assessment.is_open, 0) = 1
		ORDER BY action.name
		""",
		{"analysis_date": analysis_date, "follow_up_days": follow_up_days},
		as_dict=True,
	)


def escalate_stale_action(row, analysis_date):
	"""Propose the next step for one stale Collection Action.

	Returns a dict with status "escalated" | "skipped_already_escalated" |
	"skipped_top_of_ladder". Raises on unexpected errors - the caller
	(run_follow_up_check) wraps each row in its own try/except.
	"""

	if row.action_type == ESCALATION_ACTION_TYPE:
		return {"collection_action": row.action_name, "status": "skipped_top_of_ladder"}

	if collection_action_exists(row.external_invoice_id, ESCALATION_ACTION_TYPE):
		return {"collection_action": row.action_name, "status": "skipped_already_escalated"}

	days_stale = date_diff(analysis_date, row.due_date)

	doc = frappe.new_doc(ACTION_DOCTYPE)
	doc.update(
		{
			"receivables_customer": row.receivables_customer,
			"receivables_invoice": row.receivables_invoice,
			"invoice_risk_assessment": row.invoice_risk_assessment,
			"external_invoice_id": row.external_invoice_id,
			"customer_id": row.customer_id,
			"customer_name": row.customer_name,
			"action_type": ESCALATION_ACTION_TYPE,
			"priority": ESCALATION_PRIORITY,
			"status": "Proposed",
			"due_date": analysis_date,
			"notes": (
				f"Auto-escalated: Collection Action {row.action_name} ({row.action_type}) "
				f"had no resolution {days_stale} days past its due date."
			),
			"auto_generated": 1,
			"active_invoice_key": get_active_invoice_key(row.external_invoice_id, ESCALATION_ACTION_TYPE),
			"created_from_risk_score": row.risk_score or 0,
			"last_updated_on": now_datetime(),
		}
	)
	doc.save(ignore_permissions=True)

	log_collection_action_event(
		collection_action_name=doc.name,
		reason=(
			f"Auto-proposed escalation: Collection Action {row.action_name} had no "
			f"resolution {days_stale} days after its due date."
		),
		source="Pipeline",
		customer_id=row.customer_id,
		external_invoice_id=row.external_invoice_id,
	)

	return {
		"collection_action": doc.name,
		"status": "escalated",
		"source_action": row.action_name,
	}


def run_follow_up_check(analysis_date=None):
	"""Propose an escalation for every stale, approved Collection Action.

	Never raises - each row is independent so one bad row cannot crash the batch
	(mirrors generate_ai_drafts_for_proposed_actions). Escalations created here are
	left at status="Proposed"; generate_ai_drafts_for_proposed_actions() picks them
	up automatically when it runs later in the same pipeline.
	"""

	analysis_date = getdate(analysis_date) if analysis_date else get_analysis_date()
	follow_up_days = get_follow_up_days()

	summary = {
		"analysis_date": str(analysis_date),
		"follow_up_days": follow_up_days,
		"actions_checked": 0,
		"actions_escalated": 0,
		"actions_skipped_already_escalated": 0,
		"actions_skipped_top_of_ladder": 0,
		"actions_failed": 0,
		"errors": [],
	}

	stale_actions = get_stale_collection_actions(analysis_date, follow_up_days)

	for row in stale_actions:
		summary["actions_checked"] += 1

		try:
			result = escalate_stale_action(row, analysis_date)
		except Exception:
			summary["actions_failed"] += 1
			error = {"collection_action": row.action_name, "error": frappe.get_traceback()}
			summary["errors"].append(error)
			frappe.log_error(
				title=f"Follow-up escalation failed: {row.action_name}",
				message=error["error"],
			)
			continue

		if result["status"] == "escalated":
			summary["actions_escalated"] += 1
		elif result["status"] == "skipped_already_escalated":
			summary["actions_skipped_already_escalated"] += 1
		elif result["status"] == "skipped_top_of_ladder":
			summary["actions_skipped_top_of_ladder"] += 1

		if summary["actions_escalated"] and summary["actions_escalated"] % BATCH_SIZE == 0:
			frappe.db.commit()

	frappe.db.commit()
	return summary


def _safe_positive_int(value, default):
	if value in (None, ""):
		return default

	try:
		parsed = int(value)
	except (TypeError, ValueError):
		return default

	return parsed if parsed > 0 else default

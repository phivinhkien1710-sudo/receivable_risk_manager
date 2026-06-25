import frappe
from frappe.utils import now_datetime


AUDIT_DOCTYPE = "Risk Audit Log"


def log_risk_change(
	reference_doctype,
	reference_name,
	entity_type,
	previous_score,
	new_score,
	previous_level,
	new_level,
	reason,
	source,
	customer_id=None,
	external_invoice_id=None,
):
	"""Create an audit log only when risk score or level changes."""

	previous_score = _safe_int(previous_score)
	new_score = _safe_int(new_score)
	previous_level = previous_level or ""
	new_level = new_level or "Low"

	if previous_score == new_score and previous_level == new_level:
		return None

	try:
		doc = frappe.new_doc(AUDIT_DOCTYPE)
		doc.update(
			{
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"entity_type": entity_type,
				"customer_id": customer_id,
				"external_invoice_id": external_invoice_id,
				"previous_score": previous_score,
				"new_score": new_score,
				"previous_level": previous_level,
				"new_level": new_level,
				"reason": reason,
				"source": source,
				"calculated_on": now_datetime(),
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name
	except Exception:
		frappe.log_error(
			title=f"Risk audit log failed for {reference_doctype} {reference_name}",
			message=frappe.get_traceback(),
		)
		return None

def _safe_int(value):
	if value in (None, ""):
		return 0

	try:
		return int(value)
	except (TypeError, ValueError):
		return 0

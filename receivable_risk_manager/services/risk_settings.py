import frappe

from receivable_risk_manager.services.risk_scoring import get_default_scoring_settings


RISK_SETTINGS_DOCTYPE = "Risk Settings"


def get_scoring_settings() -> dict:
	"""Return scoring settings as a plain dictionary for pure scoring functions.

	The Risk Settings DocType intentionally exposes a small business-friendly set
	of controls. This adapter maps those coarse controls onto the more detailed
	pure-Python scoring configuration while keeping sensible defaults for rules
	that are not exposed in the UI yet.
	"""

	settings = get_default_scoring_settings()
	risk_settings = frappe.get_single(RISK_SETTINGS_DOCTYPE)

	medium_threshold = _safe_number(risk_settings.medium_risk_threshold, settings["medium_risk_threshold"])
	high_threshold = _safe_number(risk_settings.high_risk_threshold, settings["high_risk_threshold"])
	late_payment_weight = _safe_number(risk_settings.late_payment_weight, settings["customer_late_payment_medium_weight"])
	overdue_weight = _safe_number(risk_settings.overdue_weight, settings["invoice_overdue_medium_weight"])
	high_outstanding_weight = _safe_number(
		risk_settings.high_outstanding_weight,
		settings["customer_open_amount_high_weight"],
	)
	multiple_unpaid_weight = _safe_number(
		risk_settings.multiple_unpaid_weight,
		settings["customer_open_invoice_medium_weight"],
	)
	unusually_large_invoice_weight = _safe_number(
		risk_settings.unusually_large_invoice_weight,
		settings["invoice_amount_low_weight"],
	)

	settings.update(
		{
			"medium_risk_threshold": medium_threshold,
			"high_risk_threshold": high_threshold,
			"customer_late_payment_medium_weight": late_payment_weight,
			"customer_late_payment_high_weight": late_payment_weight + 10,
			"invoice_overdue_any_weight": round(overdue_weight / 4),
			"invoice_overdue_low_weight": round(overdue_weight / 2),
			"invoice_overdue_medium_weight": overdue_weight,
			"invoice_overdue_high_weight": overdue_weight + 10,
			"customer_open_amount_low_weight": round(high_outstanding_weight / 2),
			"customer_open_amount_medium_weight": round(high_outstanding_weight * 0.75),
			"customer_open_amount_high_weight": high_outstanding_weight,
			"customer_open_invoice_low_weight": round(multiple_unpaid_weight / 2),
			"customer_open_invoice_medium_weight": multiple_unpaid_weight,
			"customer_open_invoice_high_weight": multiple_unpaid_weight + 5,
			"invoice_amount_low_weight": unusually_large_invoice_weight,
			"invoice_amount_medium_weight": unusually_large_invoice_weight + 5,
			"invoice_amount_high_weight": unusually_large_invoice_weight + 10,
		}
	)

	return settings


def _safe_number(value, default):
	if value in (None, ""):
		return default

	try:
		return float(value)
	except (TypeError, ValueError):
		return default

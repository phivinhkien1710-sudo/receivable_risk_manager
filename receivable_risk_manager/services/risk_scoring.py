DEFAULT_SCORING_SETTINGS = {
	"medium_risk_threshold": 40,
	"high_risk_threshold": 70,
	"customer_late_payment_high_rate": 50,
	"customer_late_payment_medium_rate": 30,
	"customer_late_payment_high_weight": 25,
	"customer_late_payment_medium_weight": 15,
	"customer_average_delay_high_days": 15,
	"customer_average_delay_medium_days": 7,
	"customer_average_delay_low_days": 3,
	"customer_average_delay_high_weight": 20,
	"customer_average_delay_medium_weight": 12,
	"customer_average_delay_low_weight": 5,
	"customer_open_invoice_high_count": 10,
	"customer_open_invoice_medium_count": 3,
	"customer_open_invoice_low_count": 1,
	"customer_open_invoice_high_weight": 15,
	"customer_open_invoice_medium_weight": 10,
	"customer_open_invoice_low_weight": 5,
	"customer_open_amount_high_multiplier": 5,
	"customer_open_amount_medium_multiplier": 3,
	"customer_open_amount_low_multiplier": 1.5,
	"customer_open_amount_high_weight": 20,
	"customer_open_amount_medium_weight": 15,
	"customer_open_amount_low_weight": 10,
	"customer_limited_history_closed_invoice_count": 3,
	"customer_limited_history_payment_behavior_cap": 25,
	"customer_no_closed_invoice_weight": 10,
	"invoice_overdue_high_days": 60,
	"invoice_overdue_medium_days": 30,
	"invoice_overdue_low_days": 15,
	"invoice_overdue_any_weight": 8,
	"invoice_overdue_high_weight": 35,
	"invoice_overdue_medium_weight": 25,
	"invoice_overdue_low_weight": 15,
	"invoice_customer_high_risk_weight": 30,
	"invoice_customer_medium_risk_weight": 15,
	"invoice_amount_high_multiplier": 5,
	"invoice_amount_medium_multiplier": 3,
	"invoice_amount_low_multiplier": 1.5,
	"invoice_amount_high_weight": 20,
	"invoice_amount_medium_weight": 15,
	"invoice_amount_low_weight": 10,
}


def get_default_scoring_settings():
	"""Return a copy of the default pure-Python scoring settings."""

	return dict(DEFAULT_SCORING_SETTINGS)


def get_risk_level(score, settings=None):
	"""Return the risk level for a score from 0 to 100."""

	settings = _merge_settings(settings)
	score = _safe_number(score)
	score = max(0, min(100, score))

	if score >= settings["high_risk_threshold"]:
		return "High"
	if score >= settings["medium_risk_threshold"]:
		return "Medium"
	return "Low"


def calculate_average_invoice_amount(total_invoice_amount, total_invoices):
	"""Return average invoice amount, safely handling missing or zero invoices."""

	total_invoice_amount = _safe_number(total_invoice_amount)
	total_invoices = _safe_number(total_invoices)

	if total_invoices <= 0:
		return 0

	return total_invoice_amount / total_invoices


def calculate_customer_risk(metrics, settings=None):
	"""Calculate rule-based customer risk from aggregate receivables metrics.

	Args:
	    metrics (dict): Customer aggregate metrics from Receivables Customer.

	Returns:
	    dict: risk_score, risk_level, risk_explanation, and risk_confidence.
	"""

	metrics = metrics or {}
	settings = _merge_settings(settings)

	total_invoices = _safe_number(metrics.get("total_invoices"))
	closed_invoice_count = _safe_number(metrics.get("closed_invoice_count"))
	open_invoice_count = _safe_number(metrics.get("open_invoice_count"))
	total_invoice_amount = _safe_number(metrics.get("total_invoice_amount"))
	open_amount = _safe_number(metrics.get("open_amount"))
	average_payment_delay = _safe_number(metrics.get("average_payment_delay"))
	late_payment_rate = _safe_number(metrics.get("late_payment_rate"))

	average_invoice_amount = calculate_average_invoice_amount(
		total_invoice_amount=total_invoice_amount,
		total_invoices=total_invoices,
	)

	payment_behavior_score = 0
	exposure_score = 0
	data_confidence_score = 0
	reasons = []
	risk_confidence = get_risk_confidence(closed_invoice_count)

	if late_payment_rate > settings["customer_late_payment_high_rate"]:
		weight = settings["customer_late_payment_high_weight"]
		payment_behavior_score += weight
		reasons.append(
			f"Late payment rate is high at {_format_percent(late_payment_rate)}, adding {_format_count(weight)} points."
		)
	elif late_payment_rate > settings["customer_late_payment_medium_rate"]:
		weight = settings["customer_late_payment_medium_weight"]
		payment_behavior_score += weight
		reasons.append(
			f"Late payment rate is elevated at {_format_percent(late_payment_rate)}, adding {_format_count(weight)} points."
		)

	if average_payment_delay > settings["customer_average_delay_high_days"]:
		weight = settings["customer_average_delay_high_weight"]
		payment_behavior_score += weight
		reasons.append(
			f"Average payment delay is high at {_format_number(average_payment_delay)} days, adding {_format_count(weight)} points."
		)
	elif average_payment_delay > settings["customer_average_delay_medium_days"]:
		weight = settings["customer_average_delay_medium_weight"]
		payment_behavior_score += weight
		reasons.append(
			f"Average payment delay is elevated at {_format_number(average_payment_delay)} days, adding {_format_count(weight)} points."
		)
	elif average_payment_delay > settings["customer_average_delay_low_days"]:
		weight = settings["customer_average_delay_low_weight"]
		payment_behavior_score += weight
		reasons.append(
			f"Average payment delay is slightly elevated at {_format_number(average_payment_delay)} days, adding {_format_count(weight)} points."
		)

	if closed_invoice_count < settings["customer_limited_history_closed_invoice_count"]:
		limited_history_cap = settings["customer_limited_history_payment_behavior_cap"]
		if payment_behavior_score > limited_history_cap:
			payment_behavior_score = limited_history_cap
		reasons.append(
			f"Payment history is limited, so confidence is low and payment behavior risk is capped at {_format_count(limited_history_cap)} points."
		)

	if open_invoice_count >= settings["customer_open_invoice_high_count"]:
		weight = settings["customer_open_invoice_high_weight"]
		exposure_score += weight
		reasons.append(
			f"Customer has {_format_count(open_invoice_count)} open invoices, adding {_format_count(weight)} points."
		)
	elif open_invoice_count >= settings["customer_open_invoice_medium_count"]:
		weight = settings["customer_open_invoice_medium_weight"]
		exposure_score += weight
		reasons.append(
			f"Customer has {_format_count(open_invoice_count)} open invoices, adding {_format_count(weight)} points."
		)
	elif open_invoice_count >= settings["customer_open_invoice_low_count"]:
		weight = settings["customer_open_invoice_low_weight"]
		exposure_score += weight
		reasons.append(
			f"Customer has {_format_count(open_invoice_count)} open invoice, adding {_format_count(weight)} points."
		)

	if average_invoice_amount > 0:
		if open_amount > average_invoice_amount * settings["customer_open_amount_high_multiplier"]:
			weight = settings["customer_open_amount_high_weight"]
			exposure_score += weight
			reasons.append(
				f"Open amount is more than {_format_multiplier(settings['customer_open_amount_high_multiplier'])} times the customer's average invoice amount, adding {_format_count(weight)} points."
			)
		elif open_amount > average_invoice_amount * settings["customer_open_amount_medium_multiplier"]:
			weight = settings["customer_open_amount_medium_weight"]
			exposure_score += weight
			reasons.append(
				f"Open amount is more than {_format_multiplier(settings['customer_open_amount_medium_multiplier'])} times the customer's average invoice amount, adding {_format_count(weight)} points."
			)
		elif open_amount > average_invoice_amount * settings["customer_open_amount_low_multiplier"]:
			weight = settings["customer_open_amount_low_weight"]
			exposure_score += weight
			reasons.append(
				f"Open amount is more than {_format_multiplier(settings['customer_open_amount_low_multiplier'])} times the customer's average invoice amount, adding {_format_count(weight)} points."
			)

	if closed_invoice_count == 0:
		weight = settings["customer_no_closed_invoice_weight"]
		data_confidence_score += weight
		reasons.append(f"Customer has no closed invoice history, adding {_format_count(weight)} points.")

	score = payment_behavior_score + exposure_score + data_confidence_score
	score = int(max(0, min(100, score)))
	risk_level = get_risk_level(score, settings=settings)

	return {
		"risk_score": score,
		"risk_level": risk_level,
		"risk_explanation": _build_explanation(reasons, risk_level),
		"risk_confidence": risk_confidence,
	}


def calculate_invoice_risk(metrics, settings=None):
	"""Calculate rule-based risk for one invoice.

	Args:
	    metrics (dict): Invoice-level metrics.

	Returns:
	    dict: risk_score, risk_level, suggested_action, and explanation.
	"""

	metrics = metrics or {}
	settings = _merge_settings(settings)

	days_overdue = _safe_number(metrics.get("days_overdue"))
	invoice_amount = _safe_number(metrics.get("invoice_amount"))
	average_invoice_amount = _safe_number(metrics.get("average_invoice_amount"))
	customer_risk_level = _safe_text(metrics.get("customer_risk_level"))

	score = 0
	reasons = []

	if days_overdue > settings["invoice_overdue_high_days"]:
		weight = settings["invoice_overdue_high_weight"]
		score += weight
		reasons.append(
			f"Invoice is {_format_number(days_overdue)} days overdue, adding {_format_count(weight)} points."
		)
	elif days_overdue > settings["invoice_overdue_medium_days"]:
		weight = settings["invoice_overdue_medium_weight"]
		score += weight
		reasons.append(
			f"Invoice is {_format_number(days_overdue)} days overdue, adding {_format_count(weight)} points."
		)
	elif days_overdue > settings["invoice_overdue_low_days"]:
		weight = settings["invoice_overdue_low_weight"]
		score += weight
		reasons.append(
			f"Invoice is {_format_number(days_overdue)} days overdue, adding {_format_count(weight)} points."
		)
	elif days_overdue > 0:
		weight = settings["invoice_overdue_any_weight"]
		score += weight
		reasons.append(
			f"Invoice is {_format_number(days_overdue)} days overdue, adding {_format_count(weight)} points."
		)

	if customer_risk_level == "High":
		weight = settings["invoice_customer_high_risk_weight"]
		score += weight
		reasons.append(f"Customer risk level is High, adding {_format_count(weight)} points.")
	elif customer_risk_level == "Medium":
		weight = settings["invoice_customer_medium_risk_weight"]
		score += weight
		reasons.append(f"Customer risk level is Medium, adding {_format_count(weight)} points.")
	elif customer_risk_level == "Low":
		reasons.append("Customer risk level is Low, adding 0 points.")

	if average_invoice_amount > 0:
		if invoice_amount > average_invoice_amount * settings["invoice_amount_high_multiplier"]:
			weight = settings["invoice_amount_high_weight"]
			score += weight
			reasons.append(
				f"Invoice amount is more than {_format_multiplier(settings['invoice_amount_high_multiplier'])} times the customer's average invoice amount, adding {_format_count(weight)} points."
			)
		elif invoice_amount > average_invoice_amount * settings["invoice_amount_medium_multiplier"]:
			weight = settings["invoice_amount_medium_weight"]
			score += weight
			reasons.append(
				f"Invoice amount is more than {_format_multiplier(settings['invoice_amount_medium_multiplier'])} times the customer's average invoice amount, adding {_format_count(weight)} points."
			)
		elif invoice_amount > average_invoice_amount * settings["invoice_amount_low_multiplier"]:
			weight = settings["invoice_amount_low_weight"]
			score += weight
			reasons.append(
				f"Invoice amount is more than {_format_multiplier(settings['invoice_amount_low_multiplier'])} times the customer's average invoice amount, adding {_format_count(weight)} points."
			)

	score = int(max(0, min(100, score)))
	risk_level = get_risk_level(score, settings=settings)
	suggested_action = get_invoice_suggested_action(risk_level, days_overdue, settings=settings)

	return {
		"risk_score": score,
		"risk_level": risk_level,
		"suggested_action": suggested_action,
		"explanation": _build_invoice_explanation(reasons, risk_level, suggested_action),
	}


def get_invoice_suggested_action(risk_level, days_overdue, settings=None):
	settings = _merge_settings(settings)

	if risk_level == "High" and days_overdue > settings["invoice_overdue_medium_days"]:
		return "Escalate Collection"
	if risk_level == "High":
		return "Immediate Follow-up"
	if risk_level == "Medium":
		return "Send Reminder"
	return "Monitor"


def get_risk_confidence(closed_invoice_count):
	"""Return confidence level based on amount of closed invoice history."""

	closed_invoice_count = _safe_number(closed_invoice_count)

	if closed_invoice_count >= 10:
		return "High"
	if closed_invoice_count >= 3:
		return "Medium"
	return "Low"


def _safe_number(value):
	"""Convert missing or invalid values to 0."""

	if value is None or value == "":
		return 0

	try:
		return float(value)
	except (TypeError, ValueError):
		return 0


def _merge_settings(settings=None):
	merged_settings = get_default_scoring_settings()
	if not settings:
		return merged_settings

	for key, value in settings.items():
		if key not in merged_settings:
			continue
		merged_settings[key] = _safe_number(value)

	return merged_settings


def _safe_text(value):
	if value is None:
		return ""
	return str(value).strip()


def _build_explanation(reasons, risk_level):
	if not reasons:
		return f"No risk rules were triggered. Customer is classified as {risk_level} risk."

	return " ".join(reasons) + f" Final classification: {risk_level} risk."


def _build_invoice_explanation(reasons, risk_level, suggested_action):
	if not reasons:
		return (
			f"No invoice risk rules were triggered. Invoice is classified as {risk_level} risk. "
			f"Suggested action: {suggested_action}."
		)

	return (
		" ".join(reasons)
		+ f" Final classification: {risk_level} risk. Suggested action: {suggested_action}."
	)


def _format_percent(value):
	return f"{value:.1f}%"


def _format_number(value):
	return f"{value:.1f}"


def _format_count(value):
	return str(int(value))


def _format_multiplier(value):
	value = _safe_number(value)
	if value == 5:
		return "five"
	if value == 3:
		return "three"
	return _format_number(value)

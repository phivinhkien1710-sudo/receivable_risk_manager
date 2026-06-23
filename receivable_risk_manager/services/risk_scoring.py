def get_risk_level(score):
	"""Return the risk level for a score from 0 to 100."""

	score = _safe_number(score)
	score = max(0, min(100, score))

	if score >= 70:
		return "High"
	if score >= 40:
		return "Medium"
	return "Low"


def calculate_average_invoice_amount(total_invoice_amount, total_invoices):
	"""Return average invoice amount, safely handling missing or zero invoices."""

	total_invoice_amount = _safe_number(total_invoice_amount)
	total_invoices = _safe_number(total_invoices)

	if total_invoices <= 0:
		return 0

	return total_invoice_amount / total_invoices


def calculate_customer_risk(metrics):
	"""Calculate rule-based customer risk from aggregate receivables metrics.

	Args:
	    metrics (dict): Customer aggregate metrics from Receivables Customer.

	Returns:
	    dict: risk_score, risk_level, risk_explanation, and risk_confidence.
	"""

	metrics = metrics or {}

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

	if late_payment_rate > 50:
		payment_behavior_score += 25
		reasons.append(
			f"Late payment rate is high at {_format_percent(late_payment_rate)}, adding 25 points."
		)
	elif late_payment_rate > 30:
		payment_behavior_score += 15
		reasons.append(
			f"Late payment rate is elevated at {_format_percent(late_payment_rate)}, adding 15 points."
		)

	if average_payment_delay > 15:
		payment_behavior_score += 20
		reasons.append(
			f"Average payment delay is high at {_format_number(average_payment_delay)} days, adding 20 points."
		)
	elif average_payment_delay > 7:
		payment_behavior_score += 12
		reasons.append(
			f"Average payment delay is elevated at {_format_number(average_payment_delay)} days, adding 12 points."
		)
	elif average_payment_delay > 3:
		payment_behavior_score += 5
		reasons.append(
			f"Average payment delay is slightly elevated at {_format_number(average_payment_delay)} days, adding 5 points."
		)

	if closed_invoice_count < 3:
		if payment_behavior_score > 25:
			payment_behavior_score = 25
		reasons.append(
			"Payment history is limited, so confidence is low and payment behavior risk is capped at 25 points."
		)

	if open_invoice_count >= 10:
		exposure_score += 15
		reasons.append(
			f"Customer has {_format_count(open_invoice_count)} open invoices, adding 15 points."
		)
	elif open_invoice_count >= 3:
		exposure_score += 10
		reasons.append(
			f"Customer has {_format_count(open_invoice_count)} open invoices, adding 10 points."
		)
	elif open_invoice_count >= 1:
		exposure_score += 5
		reasons.append(
			f"Customer has {_format_count(open_invoice_count)} open invoice, adding 5 points."
		)

	if average_invoice_amount > 0:
		if open_amount > average_invoice_amount * 5:
			exposure_score += 20
			reasons.append(
				"Open amount is more than five times the customer's average invoice amount, adding 20 points."
			)
		elif open_amount > average_invoice_amount * 3:
			exposure_score += 15
			reasons.append(
				"Open amount is more than three times the customer's average invoice amount, adding 15 points."
			)
		elif open_amount > average_invoice_amount * 1.5:
			exposure_score += 10
			reasons.append(
				"Open amount is more than 1.5 times the customer's average invoice amount, adding 10 points."
			)

	if closed_invoice_count == 0:
		data_confidence_score += 10
		reasons.append("Customer has no closed invoice history, adding 10 points.")

	score = payment_behavior_score + exposure_score + data_confidence_score
	score = int(max(0, min(100, score)))
	risk_level = get_risk_level(score)

	return {
		"risk_score": score,
		"risk_level": risk_level,
		"risk_explanation": _build_explanation(reasons, risk_level),
		"risk_confidence": risk_confidence,
	}


def calculate_invoice_risk(metrics):
	"""Calculate rule-based risk for one invoice.

	Args:
	    metrics (dict): Invoice-level metrics.

	Returns:
	    dict: risk_score, risk_level, suggested_action, and explanation.
	"""

	metrics = metrics or {}

	days_overdue = _safe_number(metrics.get("days_overdue"))
	invoice_amount = _safe_number(metrics.get("invoice_amount"))
	average_invoice_amount = _safe_number(metrics.get("average_invoice_amount"))
	customer_risk_level = _safe_text(metrics.get("customer_risk_level"))

	score = 0
	reasons = []

	if days_overdue > 60:
		score += 35
		reasons.append(
			f"Invoice is {_format_number(days_overdue)} days overdue, adding 35 points."
		)
	elif days_overdue > 30:
		score += 25
		reasons.append(
			f"Invoice is {_format_number(days_overdue)} days overdue, adding 25 points."
		)
	elif days_overdue > 15:
		score += 15
		reasons.append(
			f"Invoice is {_format_number(days_overdue)} days overdue, adding 15 points."
		)
	elif days_overdue > 0:
		score += 8
		reasons.append(
			f"Invoice is {_format_number(days_overdue)} days overdue, adding 8 points."
		)

	if customer_risk_level == "High":
		score += 30
		reasons.append("Customer risk level is High, adding 30 points.")
	elif customer_risk_level == "Medium":
		score += 15
		reasons.append("Customer risk level is Medium, adding 15 points.")
	elif customer_risk_level == "Low":
		reasons.append("Customer risk level is Low, adding 0 points.")

	if average_invoice_amount > 0:
		if invoice_amount > average_invoice_amount * 5:
			score += 20
			reasons.append(
				"Invoice amount is more than five times the customer's average invoice amount, adding 20 points."
			)
		elif invoice_amount > average_invoice_amount * 3:
			score += 15
			reasons.append(
				"Invoice amount is more than three times the customer's average invoice amount, adding 15 points."
			)
		elif invoice_amount > average_invoice_amount * 1.5:
			score += 10
			reasons.append(
				"Invoice amount is more than 1.5 times the customer's average invoice amount, adding 10 points."
			)

	score = int(max(0, min(100, score)))
	risk_level = get_risk_level(score)
	suggested_action = get_invoice_suggested_action(risk_level, days_overdue)

	return {
		"risk_score": score,
		"risk_level": risk_level,
		"suggested_action": suggested_action,
		"explanation": _build_invoice_explanation(reasons, risk_level, suggested_action),
	}


def get_invoice_suggested_action(risk_level, days_overdue):
	if risk_level == "High" and days_overdue > 30:
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

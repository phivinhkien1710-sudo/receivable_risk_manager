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
	    dict: risk_score, risk_level, and risk_explanation.
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

	score = 0
	reasons = []

	if late_payment_rate > 50:
		score += 30
		reasons.append(
			f"Late payment rate is high at {_format_percent(late_payment_rate)}, adding 30 points."
		)
	elif late_payment_rate > 30:
		score += 20
		reasons.append(
			f"Late payment rate is elevated at {_format_percent(late_payment_rate)}, adding 20 points."
		)

	if average_payment_delay > 10:
		score += 25
		reasons.append(
			f"Average payment delay is high at {_format_number(average_payment_delay)} days, adding 25 points."
		)
	elif average_payment_delay > 5:
		score += 15
		reasons.append(
			f"Average payment delay is elevated at {_format_number(average_payment_delay)} days, adding 15 points."
		)

	if open_invoice_count > 5:
		score += 15
		reasons.append(
			f"Customer has {_format_count(open_invoice_count)} open invoices, adding 15 points."
		)

	if average_invoice_amount > 0 and open_amount > average_invoice_amount * 3:
		score += 20
		reasons.append(
			"Open amount is more than three times the customer's average invoice amount, adding 20 points."
		)

	if closed_invoice_count == 0:
		score += 10
		reasons.append("Customer has no closed invoice history, adding 10 points.")

	score = int(max(0, min(100, score)))
	risk_level = get_risk_level(score)

	return {
		"risk_score": score,
		"risk_level": risk_level,
		"risk_explanation": _build_explanation(reasons, risk_level),
	}


def _safe_number(value):
	"""Convert missing or invalid values to 0."""

	if value is None or value == "":
		return 0

	try:
		return float(value)
	except (TypeError, ValueError):
		return 0


def _build_explanation(reasons, risk_level):
	if not reasons:
		return f"No risk rules were triggered. Customer is classified as {risk_level} risk."

	return " ".join(reasons) + f" Final classification: {risk_level} risk."


def _format_percent(value):
	return f"{value:.1f}%"


def _format_number(value):
	return f"{value:.1f}"


def _format_count(value):
	return str(int(value))

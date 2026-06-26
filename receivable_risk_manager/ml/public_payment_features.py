import pandas as pd


VALUE_BUCKET_COLUMNS = [
	"value_paid_within_30",
	"value_paid_31_60",
	"value_paid_later_60",
]


def build_company_payment_features(df):
	"""Create company-level payment behavior features.

	The source data is company/reporting-period level, not invoice level. Value
	features are therefore named as reported payment values, not invoice totals.
	"""

	result = df.copy()

	result["reported_paid_invoice_value"] = result.apply(
		calculate_reported_paid_invoice_value,
		axis=1,
	)
	result["late_payment_value"] = result.apply(calculate_late_payment_value, axis=1)
	result["value_paid_later_than_60"] = result["value_paid_later_60"]
	result["value_paid_later_than_terms"] = result["value_paid_later_than_terms"]
	result["share_value_late_if_available"] = result.apply(
		calculate_share_value_late,
		axis=1,
	)
	result["payment_speed_score"] = result.apply(calculate_payment_speed_score, axis=1)
	result["payment_reliability_score"] = result.apply(
		calculate_payment_reliability_score,
		axis=1,
	)
	result["payment_behavior_score"] = result.apply(
		calculate_payment_behavior_score,
		axis=1,
	)
	result["public_payment_risk_band"] = result.apply(
		assign_public_payment_risk_band,
		axis=1,
	)

	if "company_number" in result.columns:
		result["company_reporting_count"] = result.groupby("company_number")[
			"company_number"
		].transform("count")
	else:
		result["company_reporting_count"] = 1

	return result


def calculate_reported_paid_invoice_value(row):
	"""Sum reported paid invoice value buckets when all buckets are available."""

	values = [to_float_or_none(row.get(column)) for column in VALUE_BUCKET_COLUMNS]

	if any(value is None for value in values):
		return pd.NA

	return sum(values)


def calculate_late_payment_value(row):
	"""Return reported value paid later than agreed terms, when available."""

	return to_float_or_na(row.get("value_paid_later_than_terms"))


def calculate_share_value_late(row):
	total_value = to_float_or_none(row.get("reported_paid_invoice_value"))
	late_value = to_float_or_none(row.get("late_payment_value"))

	if total_value in (None, 0) or late_value is None:
		return pd.NA

	return min(max((late_value / total_value) * 100, 0), 100)


def calculate_payment_speed_score(row):
	"""Score payment speed from 0 to 100, where faster payment is better."""

	avg_days_to_pay = to_float_or_none(row.get("avg_days_to_pay"))
	if avg_days_to_pay is None:
		return pd.NA

	return round(max(0, min(100, 100 - avg_days_to_pay)), 2)


def calculate_payment_reliability_score(row):
	"""Score payment reliability from 0 to 100, based on agreed terms behavior."""

	pct_not_paid_within_terms = to_float_or_none(row.get("pct_not_paid_within_terms"))
	if pct_not_paid_within_terms is None:
		return pd.NA

	return round(max(0, min(100, 100 - pct_not_paid_within_terms)), 2)


def calculate_payment_behavior_score(row):
	"""Return an explainable composite score where higher means better behavior."""

	speed_score = to_float_or_none(row.get("payment_speed_score"))
	reliability_score = to_float_or_none(row.get("payment_reliability_score"))

	if speed_score is None and reliability_score is None:
		return pd.NA
	if speed_score is None:
		return round(reliability_score, 2)
	if reliability_score is None:
		return round(speed_score, 2)

	return round((speed_score * 0.5) + (reliability_score * 0.5), 2)


def assign_public_payment_risk_band(row):
	"""Assign a simple public payment risk band from behavior metrics."""

	avg_days_to_pay = to_float_or_none(row.get("avg_days_to_pay"))
	pct_not_paid_within_terms = to_float_or_none(row.get("pct_not_paid_within_terms"))

	if avg_days_to_pay is None and pct_not_paid_within_terms is None:
		return "Unknown"

	if (avg_days_to_pay is not None and avg_days_to_pay > 60) or (
		pct_not_paid_within_terms is not None and pct_not_paid_within_terms > 25
	):
		return "High"

	if (avg_days_to_pay is not None and avg_days_to_pay > 30) or (
		pct_not_paid_within_terms is not None and pct_not_paid_within_terms > 10
	):
		return "Medium"

	return "Low"


def to_float_or_na(value):
	value = to_float_or_none(value)
	return pd.NA if value is None else value


def to_float_or_none(value):
	if value is None or pd.isna(value):
		return None

	try:
		return float(value)
	except (TypeError, ValueError):
		return None

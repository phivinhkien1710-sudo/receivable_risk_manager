import pandas as pd


PAYMENT_BUCKET_PERCENT_COLUMNS = [
	"pct_paid_within_30",
	"pct_paid_31_60",
	"pct_paid_later_60",
]

PERCENTAGE_COLUMNS = [
	"pct_paid_within_30",
	"pct_paid_31_60",
	"pct_paid_later_60",
	"pct_not_paid_within_terms",
	"pct_not_paid_due_to_dispute",
]

VALUE_COLUMNS = [
	"value_paid_within_30",
	"value_paid_31_60",
	"value_paid_later_60",
	"value_paid_later_than_terms",
]


def validate_public_payment_data(df):
	"""Return row-level quality masks and issue summary for cleaned public data."""

	issues = {
		"missing_required_fields": detect_missing_required_fields(df),
		"invalid_percentages": detect_invalid_percentages(df),
		"invalid_average_payment_days": detect_invalid_average_payment_days(df),
		"duplicate_company_periods": detect_duplicate_company_periods(df),
		"value_bucket_issues": detect_value_bucket_issues(df),
		"inconsistent_payment_terms": detect_inconsistent_payment_terms(df),
		"payment_bucket_sum_issues": detect_payment_bucket_sum_issues(df),
	}
	issues["rejected_rows"] = detect_rejected_rows(df, issues)

	return issues


def detect_missing_required_fields(df):
	required_fields = [
		"company_name",
		"company_number",
		"reporting_period_start",
		"reporting_period_end",
		"avg_days_to_pay",
	]

	return combine_masks([df[field].isna() for field in required_fields if field in df.columns], df.index)


def detect_invalid_percentages(df):
	masks = []

	for column in PERCENTAGE_COLUMNS:
		if column in df.columns:
			masks.append(df[column].notna() & ((df[column] < 0) | (df[column] > 100)))

	return combine_masks(masks, df.index)


def detect_invalid_average_payment_days(df):
	if "avg_days_to_pay" not in df.columns:
		return pd.Series(False, index=df.index)

	return df["avg_days_to_pay"].notna() & (
		(df["avg_days_to_pay"] < 0) | (df["avg_days_to_pay"] > 365)
	)


def detect_duplicate_company_periods(df):
	key_fields = ["company_number", "reporting_period_start", "reporting_period_end"]
	if not all(field in df.columns for field in key_fields):
		return pd.Series(False, index=df.index)

	return df.duplicated(subset=key_fields, keep=False)


def detect_value_bucket_issues(df):
	masks = []

	for column in VALUE_COLUMNS:
		if column in df.columns:
			masks.append(df[column].notna() & (df[column] < 0))

	return combine_masks(masks, df.index)


def detect_inconsistent_payment_terms(df):
	required = {"shortest_standard_payment_period", "longest_standard_payment_period"}
	if not required.issubset(set(df.columns)):
		return pd.Series(False, index=df.index)

	return (
		df["shortest_standard_payment_period"].notna()
		& df["longest_standard_payment_period"].notna()
		& (df["shortest_standard_payment_period"] > df["longest_standard_payment_period"])
	)


def detect_payment_bucket_sum_issues(df):
	if not all(column in df.columns for column in PAYMENT_BUCKET_PERCENT_COLUMNS):
		return pd.Series(False, index=df.index)

	bucket_values = df[PAYMENT_BUCKET_PERCENT_COLUMNS]
	complete_bucket_rows = bucket_values.notna().all(axis=1)
	bucket_sum = bucket_values.sum(axis=1)

	return complete_bucket_rows & ((bucket_sum < 99) | (bucket_sum > 101))


def detect_rejected_rows(df, issues):
	reject_masks = [
		issues["missing_required_fields"],
		df["avg_days_to_pay"].isna()
		if "avg_days_to_pay" in df.columns
		else pd.Series(False, index=df.index),
	]

	return combine_masks(reject_masks, df.index)


def generate_data_quality_report(df, issues):
	"""Create a compact JSON-serializable data quality report."""

	report = {
		"row_count": int(len(df)),
		"column_count": int(len(df.columns)),
		"issue_counts": {},
		"missingness": {},
	}

	for issue_name, mask in issues.items():
		report["issue_counts"][issue_name] = int(mask.sum())

	for column in df.columns:
		report["missingness"][column] = int(df[column].isna().sum())

	return report


def add_quality_flags(df, issues):
	"""Add quality flag columns without dropping rows."""

	result = df.copy()
	result["is_rejected"] = issues["rejected_rows"]
	result["quality_flags"] = ""

	for issue_name, mask in issues.items():
		if issue_name == "rejected_rows":
			continue

		result.loc[mask, "quality_flags"] = result.loc[mask, "quality_flags"].apply(
			lambda current: append_flag(current, issue_name)
		)

	result["has_quality_flags"] = result["quality_flags"].ne("")

	return result


def append_flag(current, flag):
	if not current:
		return flag

	return f"{current};{flag}"


def combine_masks(masks, index):
	if not masks:
		return pd.Series(False, index=index)

	combined = pd.Series(False, index=index)
	for mask in masks:
		combined = combined | mask.fillna(False)

	return combined

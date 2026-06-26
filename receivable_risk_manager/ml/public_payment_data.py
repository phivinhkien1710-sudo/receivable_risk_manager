import argparse
import json
import re
from pathlib import Path

import pandas as pd

from receivable_risk_manager.ml.data_quality import (
	add_quality_flags,
	generate_data_quality_report,
	validate_public_payment_data,
)
from receivable_risk_manager.ml.public_payment_features import build_company_payment_features


RAW_TO_NORMALIZED_COLUMNS = {
	"Report Id": "report_id",
	"Policy Regime": "policy_regime",
	"Financial period start date": "financial_period_start_date",
	"Start date": "reporting_period_start",
	"End date": "reporting_period_end",
	"Filing date": "filing_date",
	"Company": "company_name",
	"Company number": "company_number",
	"Average time to pay": "avg_days_to_pay",
	"Total value invoices paid within 30 days": "value_paid_within_30",
	"Total value invoices paid between 31 and 60 days": "value_paid_31_60",
	"Total value invoices paid later than 60 days": "value_paid_later_60",
	"% Invoices paid within 30 days": "pct_paid_within_30",
	"% Invoices paid between 31 and 60 days": "pct_paid_31_60",
	"% Invoices paid later than 60 days": "pct_paid_later_60",
	"Total value invoices paid later than agreed terms": "value_paid_later_than_terms",
	"% Invoices not paid within agreed terms": "pct_not_paid_within_terms",
	"% Invoices not paid due to dispute": "pct_not_paid_due_to_dispute",
	"Shortest (or only) standard payment period": "shortest_standard_payment_period",
	"Longest standard payment period": "longest_standard_payment_period",
	"Standard payment terms": "standard_payment_terms",
	"Payment terms have changed": "payment_terms_have_changed",
	"Suppliers notified of changes": "suppliers_notified_of_changes",
	"Maximum contractual payment period": "maximum_contractual_payment_period",
	"Maximum contractual payment period information": "maximum_contractual_payment_period_info",
	"Other information payment terms": "other_payment_terms_info",
	"Participates in payment codes": "participates_in_payment_codes",
	"E-Invoicing offered": "e_invoicing_offered",
	"Supply-chain financing offered": "supply_chain_financing_offered",
	"URL": "source_url",
}

DATE_COLUMNS = [
	"financial_period_start_date",
	"reporting_period_start",
	"reporting_period_end",
	"filing_date",
]

NUMERIC_COLUMNS = [
	"avg_days_to_pay",
	"pct_paid_within_30",
	"pct_paid_31_60",
	"pct_paid_later_60",
	"pct_not_paid_within_terms",
	"pct_not_paid_due_to_dispute",
	"value_paid_within_30",
	"value_paid_31_60",
	"value_paid_later_60",
	"value_paid_later_than_terms",
	"shortest_standard_payment_period",
	"longest_standard_payment_period",
	"maximum_contractual_payment_period",
]

BOOLEAN_TEXT_COLUMNS = [
	"suppliers_notified_of_changes",
	"participates_in_payment_codes",
	"e_invoicing_offered",
	"supply_chain_financing_offered",
]

ML_READY_COLUMNS = [
	"original_row_index",
	"report_id",
	"policy_regime",
	"company_name",
	"company_number",
	"reporting_period_start",
	"reporting_period_end",
	"filing_date",
	"reporting_period",
	"reporting_period_length_days",
	"company_reporting_count",
	"avg_days_to_pay",
	"pct_paid_within_30",
	"pct_paid_31_60",
	"pct_paid_later_60",
	"pct_not_paid_within_terms",
	"pct_not_paid_due_to_dispute",
	"value_paid_within_30",
	"value_paid_31_60",
	"value_paid_later_60",
	"value_paid_later_than_terms",
	"reported_paid_invoice_value",
	"value_paid_later_than_60",
	"share_value_late_if_available",
	"shortest_standard_payment_period",
	"longest_standard_payment_period",
	"maximum_contractual_payment_period",
	"standard_payment_terms",
	"payment_terms_have_changed",
	"payment_terms_changed_flag",
	"payment_terms_changed_covid_related",
	"payment_terms_changed_policy_related",
	"payment_terms_changed_supplier_related",
	"suppliers_notified_of_changes",
	"e_invoicing_offered",
	"supply_chain_financing_offered",
	"participates_in_payment_codes",
	"has_value_bucket_data",
	"has_terms_data",
	"has_quality_flags",
	"quality_flags",
	"payment_speed_score",
	"payment_reliability_score",
	"payment_behavior_score",
	"public_payment_risk_band",
	"slow_payer_label",
	"late_terms_label",
	"source_url",
]

MISSING_TOKENS = {"", "none", "null", "nan", "n/a"}


def load_public_payment_csv(path):
	"""Load the raw GOV.UK payment practices CSV as strings for deterministic cleaning."""

	return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def normalize_public_payment_columns(df):
	"""Rename raw GOV.UK columns into stable snake_case names."""

	result = df.copy()
	result.columns = [clean_column_name(column) for column in result.columns]

	clean_mapping = {
		clean_column_name(raw_column): normalized_column
		for raw_column, normalized_column in RAW_TO_NORMALIZED_COLUMNS.items()
	}
	result = result.rename(columns=clean_mapping)

	for normalized_column in RAW_TO_NORMALIZED_COLUMNS.values():
		if normalized_column not in result.columns:
			result[normalized_column] = pd.NA

	return result


def clean_public_payment_data(df):
	"""Clean types and standardize identity/date/payment fields."""

	result = df.copy()

	if "original_row_index" not in result.columns:
		result.insert(0, "original_row_index", result.index)

	for column in result.columns:
		if column != "original_row_index":
			result[column] = result[column].map(clean_text)

	for column in ("company_name", "company_number"):
		if column in result.columns:
			result[column] = result[column].map(
				standardize_company_name if column == "company_name" else standardize_company_number
			)

	for column in DATE_COLUMNS:
		if column in result.columns:
			result[column] = pd.to_datetime(
				result[column],
				format="%Y-%m-%d",
				errors="coerce",
			).dt.date

	for column in NUMERIC_COLUMNS:
		if column in result.columns:
			result[column] = pd.to_numeric(result[column].map(parse_number), errors="coerce")

	for column in BOOLEAN_TEXT_COLUMNS:
		if column in result.columns:
			result[column] = result[column].map(normalize_boolean_text)

	result = add_payment_terms_change_features(result)

	result["reporting_period"] = build_reporting_period(result)
	result["reporting_period_length_days"] = calculate_reporting_period_length(result)
	result["has_value_bucket_data"] = result[
		["value_paid_within_30", "value_paid_31_60", "value_paid_later_60"]
	].notna().all(axis=1)
	result["has_terms_data"] = result.get("standard_payment_terms", pd.Series(pd.NA, index=result.index)).notna()

	return result


def build_public_payment_features(df):
	return build_company_payment_features(df)


def create_slow_payer_labels(df):
	"""Create behavior labels for later model experiments."""

	result = df.copy()
	result["slow_payer_label"] = result["avg_days_to_pay"].map(
		lambda value: pd.NA if pd.isna(value) else int(value > 60)
	)
	result["late_terms_label"] = result["pct_not_paid_within_terms"].map(
		lambda value: pd.NA if pd.isna(value) else int(value > 25)
	)

	return result


def export_public_payment_outputs(df, output_dir):
	"""Write cleaned, flagged, ML-ready, and quality report outputs."""

	output_path = Path(output_dir)
	output_path.mkdir(parents=True, exist_ok=True)

	issues = validate_public_payment_data(df)
	flagged_df = add_quality_flags(df, issues)
	quality_report = generate_data_quality_report(flagged_df, issues)

	rejected_mask = flagged_df["is_rejected"]
	flagged_mask = flagged_df["has_quality_flags"] | flagged_df["is_rejected"]
	cleaned_df = flagged_df.loc[~rejected_mask].copy()
	flagged_rows = flagged_df.loc[flagged_mask].copy()
	ml_ready = cleaned_df[[column for column in ML_READY_COLUMNS if column in cleaned_df.columns]].copy()

	quality_report["output_counts"] = {
		"cleaned_rows": int(len(cleaned_df)),
		"flagged_rows": int(len(flagged_rows)),
		"ml_ready_rows": int(len(ml_ready)),
		"rejected_rows": int(rejected_mask.sum()),
	}

	outputs = {
		"cleaned": output_path / "public_payment_cleaned.csv",
		"flagged_rows": output_path / "public_payment_flagged_rows.csv",
		"ml_ready": output_path / "public_payment_ml_ready.csv",
		"quality_report": output_path / "public_payment_quality_report.json",
	}

	cleaned_df.to_csv(outputs["cleaned"], index=False)
	flagged_rows.to_csv(outputs["flagged_rows"], index=False)
	ml_ready.to_csv(outputs["ml_ready"], index=False)

	with outputs["quality_report"].open("w", encoding="utf-8") as report_file:
		json.dump(quality_report, report_file, indent=2, default=str)

	return {
		"cleaned_rows": int(len(cleaned_df)),
		"flagged_rows": int(len(flagged_rows)),
		"ml_ready_rows": int(len(ml_ready)),
		"rejected_rows": int(rejected_mask.sum()),
		"outputs": {key: str(value) for key, value in outputs.items()},
		"quality_report": quality_report,
	}


def process_public_payment_csv(input_path, output_dir):
	raw_df = load_public_payment_csv(input_path)
	normalized_df = normalize_public_payment_columns(raw_df)
	cleaned_df = clean_public_payment_data(normalized_df)
	featured_df = build_public_payment_features(cleaned_df)
	labeled_df = create_slow_payer_labels(featured_df)

	return export_public_payment_outputs(labeled_df, output_dir)


def clean_column_name(column):
	return str(column).strip()


def clean_text(value):
	if value is None or pd.isna(value):
		return pd.NA

	value = str(value).strip()
	if value.lower() in MISSING_TOKENS:
		return pd.NA

	return value


def standardize_company_name(value):
	if value is None or pd.isna(value):
		return pd.NA

	return re.sub(r"\s+", " ", str(value).strip()).upper()


def standardize_company_number(value):
	if value is None or pd.isna(value):
		return pd.NA

	value = str(value).strip().upper()
	return value.zfill(8) if value.isdigit() and len(value) < 8 else value


def parse_number(value):
	if value is None or pd.isna(value):
		return pd.NA

	value = str(value).strip().replace(",", "").replace("£", "").replace("%", "")
	if value.lower() in MISSING_TOKENS:
		return pd.NA
	if value.startswith("(") and value.endswith(")"):
		value = f"-{value[1:-1]}"

	try:
		return float(value)
	except ValueError:
		return pd.NA


def normalize_boolean_text(value):
	if value is None or pd.isna(value):
		return pd.NA

	value = str(value).strip()
	if value.lower() in MISSING_TOKENS:
		return pd.NA

	lower_value = value.lower()
	if lower_value in {"true", "yes", "y", "1"}:
		return True
	if lower_value in {"false", "no", "n", "0"}:
		return False

	return value


def add_payment_terms_change_features(df):
	"""Derive stable ML features from the free-text payment terms change field.

	GOV.UK reports can store either simple Yes/No values or longer prose in
	``payment_terms_have_changed``. Keeping the raw text is useful for audit, but
	training directly on it creates a brittle high-cardinality feature. These
	derived fields give the model compact, explainable signals instead.
	"""

	result = df.copy()
	source = result.get("payment_terms_have_changed", pd.Series(pd.NA, index=result.index))

	result["payment_terms_changed_flag"] = source.map(normalize_payment_terms_changed_flag)
	result["payment_terms_changed_covid_related"] = source.map(
		lambda value: int(text_contains_any(value, {"covid", "coronavirus", "pandemic", "lockdown"}))
	)
	result["payment_terms_changed_policy_related"] = source.map(
		lambda value: int(
			text_contains_any(
				value,
				{
					"policy",
					"policies",
					"term",
					"terms",
					"contract",
					"contractual",
					"standard",
					"procedure",
					"process",
				},
			)
		)
	)
	result["payment_terms_changed_supplier_related"] = source.map(
		lambda value: int(text_contains_any(value, {"supplier", "suppliers", "vendor", "vendors"}))
	)

	return result


def normalize_payment_terms_changed_flag(value):
	if value is None or pd.isna(value):
		return "Unknown"

	value = str(value).strip()
	if value.lower() in MISSING_TOKENS:
		return "Unknown"

	lower_value = value.lower()
	if lower_value in {"true", "yes", "y", "1"}:
		return "Yes"
	if lower_value in {"false", "no", "n", "0"}:
		return "No"
	if "no change" in lower_value or "not changed" in lower_value or "no changes" in lower_value:
		return "No"

	return "Yes"


def text_contains_any(value, keywords):
	if value is None or pd.isna(value):
		return False

	lower_value = str(value).lower()
	return any(keyword in lower_value for keyword in keywords)


def build_reporting_period(df):
	start = df.get("reporting_period_start", pd.Series(pd.NA, index=df.index)).astype("string")
	end = df.get("reporting_period_end", pd.Series(pd.NA, index=df.index)).astype("string")

	return start + " to " + end


def calculate_reporting_period_length(df):
	start = pd.to_datetime(df.get("reporting_period_start"), errors="coerce")
	end = pd.to_datetime(df.get("reporting_period_end"), errors="coerce")

	return (end - start).dt.days


def main():
	parser = argparse.ArgumentParser(
		description="Process GOV.UK payment practices data into ML-ready company payment features."
	)
	parser.add_argument("--input", required=True, help="Path to the raw public payment CSV.")
	parser.add_argument(
		"--output-dir",
		default="ml/data/processed",
		help="Directory for processed outputs.",
	)
	args = parser.parse_args()

	result = process_public_payment_csv(args.input, args.output_dir)
	print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
	main()

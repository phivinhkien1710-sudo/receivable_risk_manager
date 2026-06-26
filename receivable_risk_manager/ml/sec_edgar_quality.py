"""Data quality summaries for processed SEC EDGAR financial profiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


CORE_FINANCIAL_FIELDS = [
	"revenue",
	"cash",
	"assets_current",
	"liabilities_current",
	"assets",
	"liabilities",
	"net_income",
]

RATIO_FIELDS = [
	"current_ratio",
	"cash_to_current_liabilities",
	"liabilities_to_assets",
	"accounts_payable_to_revenue",
	"net_margin",
]


def load_sec_financial_profiles(path):
	"""Load processed SEC financial profiles."""

	return pd.read_csv(path, dtype={"cik": str})


def summarize_sec_financial_profiles(df):
	"""Return a read-only quality summary for processed SEC profiles."""

	total_companies = len(df)

	return {
		"total_companies": total_companies,
		"unique_ciks": safe_nunique(df, "cik"),
		"missing_entity_name": count_missing(df, "entity_name"),
		"missing_latest_filed_date": count_missing(df, "latest_filed_date"),
		"missing_latest_fiscal_period_end": count_missing(df, "latest_fiscal_period_end"),
		"missing_core_fields": {
			field: count_missing(df, field) for field in CORE_FINANCIAL_FIELDS if field in df.columns
		},
		"missing_ratio_fields": {
			field: count_missing(df, field) for field in RATIO_FIELDS if field in df.columns
		},
		"risk_band_distribution": value_counts(df, "sec_financial_risk_band"),
		"top_sic_descriptions": value_counts(df, "sic_description", limit=10),
		"companies_with_no_core_financials": count_rows_missing_all(df, CORE_FINANCIAL_FIELDS),
		"companies_with_no_ratios": count_rows_missing_all(df, RATIO_FIELDS),
		"negative_revenue_count": count_less_than(df, "revenue", 0),
		"negative_equity_count": count_less_than(df, "equity", 0),
		"extreme_current_ratio_count": count_greater_than(df, "current_ratio", 20),
		"extreme_net_margin_count": count_absolute_greater_than(df, "net_margin", 5),
	}


def write_sec_quality_report(summary, output_path):
	"""Write SEC quality summary to JSON."""

	path = Path(output_path)
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
	return path


def create_sec_quality_report(input_path, output_path):
	"""Load SEC profiles, summarize quality, and export the report."""

	df = load_sec_financial_profiles(input_path)
	summary = summarize_sec_financial_profiles(df)
	write_sec_quality_report(summary, output_path)

	return {
		"input_path": str(input_path),
		"output_path": str(output_path),
		**summary,
	}


def count_missing(df, column):
	if column not in df.columns:
		return None

	return int(df[column].isna().sum())


def safe_nunique(df, column):
	if column not in df.columns:
		return None

	return int(df[column].nunique(dropna=True))


def value_counts(df, column, limit=None):
	if column not in df.columns:
		return {}

	counts = df[column].fillna("Missing").value_counts()
	if limit:
		counts = counts.head(limit)

	return {str(key): int(value) for key, value in counts.items()}


def count_rows_missing_all(df, columns):
	existing_columns = [column for column in columns if column in df.columns]
	if not existing_columns:
		return None

	return int(df[existing_columns].isna().all(axis=1).sum())


def count_less_than(df, column, threshold):
	if column not in df.columns:
		return None

	return int((pd.to_numeric(df[column], errors="coerce") < threshold).sum())


def count_greater_than(df, column, threshold):
	if column not in df.columns:
		return None

	return int((pd.to_numeric(df[column], errors="coerce") > threshold).sum())


def count_absolute_greater_than(df, column, threshold):
	if column not in df.columns:
		return None

	values = pd.to_numeric(df[column], errors="coerce")
	return int((values.abs() > threshold).sum())


def main():
	parser = argparse.ArgumentParser(description="Create a quality report for processed SEC financial profiles.")
	parser.add_argument(
		"--input",
		default="ml/data/processed/sec_company_financial_profiles.csv",
		help="Path to processed SEC financial profiles CSV.",
	)
	parser.add_argument(
		"--output",
		default="ml/data/processed/sec_company_financial_profiles_quality_report.json",
		help="Output JSON report path.",
	)

	args = parser.parse_args()
	summary = create_sec_quality_report(args.input, args.output)
	print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
	main()

"""Process SEC EDGAR companyfacts data into company-level financial features.

This module is intentionally outside the Frappe service layer. It prepares
external public company data for later enrichment experiments, without writing
to ERPNext/Frappe DocTypes.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

import pandas as pd

from receivable_risk_manager.ml.sec_edgar_features import build_sec_company_profile


SEC_PROFILE_COLUMNS = [
	"cik",
	"entity_name",
	"sic",
	"sic_description",
	"latest_filed_date",
	"latest_fiscal_period_end",
	"revenue",
	"cash",
	"assets_current",
	"liabilities_current",
	"assets",
	"liabilities",
	"equity",
	"accounts_payable",
	"operating_income",
	"net_income",
	"current_ratio",
	"cash_to_current_liabilities",
	"liabilities_to_assets",
	"accounts_payable_to_revenue",
	"net_margin",
	"sec_financial_risk_band",
]


def load_sec_companyfacts_json(path):
	"""Load one SEC companyfacts JSON file."""

	with Path(path).open(encoding="utf-8") as json_file:
		return json.load(json_file)


def iter_sec_companyfacts(input_path, limit=None):
	"""Yield SEC companyfacts JSON objects from a file, directory, or ZIP archive."""

	path = Path(input_path)
	processed = 0

	if path.is_dir():
		json_paths = sorted(path.rglob("*.json"))
		for json_path in json_paths:
			yield load_sec_companyfacts_json(json_path)
			processed += 1
			if limit and processed >= limit:
				return
		return

	if path.suffix.lower() == ".zip":
		with zipfile.ZipFile(path) as archive:
			json_names = sorted(name for name in archive.namelist() if name.lower().endswith(".json"))
			for json_name in json_names:
				with archive.open(json_name) as json_file:
					yield json.load(json_file)
				processed += 1
				if limit and processed >= limit:
					return
		return

	if path.suffix.lower() == ".json":
		yield load_sec_companyfacts_json(path)
		return

	raise ValueError(f"Unsupported SEC input path: {path}. Use a .json file, .zip archive, or directory.")


def build_sec_financial_profiles(input_path, limit=None):
	"""Build a DataFrame of company-level financial profiles from SEC companyfacts."""

	profiles = []

	for companyfacts in iter_sec_companyfacts(input_path, limit=limit):
		profiles.append(build_sec_company_profile(companyfacts))

	result = pd.DataFrame(profiles)

	for column in SEC_PROFILE_COLUMNS:
		if column not in result.columns:
			result[column] = pd.NA

	return result[SEC_PROFILE_COLUMNS]


def export_sec_financial_profiles(df, output_path):
	"""Write SEC financial profiles to CSV."""

	path = Path(output_path)
	path.parent.mkdir(parents=True, exist_ok=True)
	df.to_csv(path, index=False)
	return path


def process_sec_companyfacts(input_path, output_path, limit=None):
	"""Build and export SEC financial profiles in one step."""

	profiles = build_sec_financial_profiles(input_path, limit=limit)
	export_path = export_sec_financial_profiles(profiles, output_path)

	return {
		"input_path": str(input_path),
		"output_path": str(export_path),
		"companies_processed": len(profiles),
		"columns": list(profiles.columns),
	}


def main():
	parser = argparse.ArgumentParser(description="Build ML-ready financial profiles from SEC companyfacts data.")
	parser.add_argument(
		"--input",
		required=True,
		help="Path to SEC companyfacts.zip, one companyfacts JSON file, or a directory of JSON files.",
	)
	parser.add_argument(
		"--output",
		default="ml/data/processed/sec_company_financial_profiles.csv",
		help="Output CSV path.",
	)
	parser.add_argument(
		"--limit",
		type=int,
		default=None,
		help="Optional number of companies to process for a quick sample run.",
	)

	args = parser.parse_args()
	summary = process_sec_companyfacts(args.input, args.output, limit=args.limit)
	print(json.dumps(summary, indent=2))


if __name__ == "__main__":
	main()

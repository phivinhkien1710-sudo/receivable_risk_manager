import tempfile
import unittest
from pathlib import Path

import pandas as pd

from receivable_risk_manager.ml.public_payment_data import (
	add_payment_terms_change_features,
	clean_public_payment_data,
	create_slow_payer_labels,
	export_public_payment_outputs,
	normalize_payment_terms_changed_flag,
	normalize_public_payment_columns,
	parse_number,
	process_public_payment_csv,
)


class TestPublicPaymentData(unittest.TestCase):
	def test_column_normalization(self):
		df = pd.DataFrame(
			[
				{
					"Company": "Acme Limited",
					"Company number": "123",
					"Average time to pay": "45",
				}
			]
		)

		result = normalize_public_payment_columns(df)

		self.assertIn("company_name", result.columns)
		self.assertIn("company_number", result.columns)
		self.assertIn("avg_days_to_pay", result.columns)

	def test_number_parsing(self):
		self.assertEqual(parse_number("£1,234.50"), 1234.5)
		self.assertEqual(parse_number("55%"), 55)
		self.assertTrue(pd.isna(parse_number("None")))

	def test_slow_payer_and_late_terms_labels(self):
		df = pd.DataFrame(
			[
				{"avg_days_to_pay": 61, "pct_not_paid_within_terms": 26},
				{"avg_days_to_pay": 30, "pct_not_paid_within_terms": 10},
			]
		)

		result = create_slow_payer_labels(df)

		self.assertEqual(result.loc[0, "slow_payer_label"], 1)
		self.assertEqual(result.loc[0, "late_terms_label"], 1)
		self.assertEqual(result.loc[1, "slow_payer_label"], 0)
		self.assertEqual(result.loc[1, "late_terms_label"], 0)

	def test_cleaning_keeps_rows_with_missing_value_bucket_fields(self):
		df = pd.DataFrame(
			[
				{
					"Company": "Acme Limited",
					"Company number": "123",
					"Start date": "2020-01-01",
					"End date": "2020-06-30",
					"Average time to pay": "45",
					"% Invoices not paid within agreed terms": "20",
				}
			]
		)

		normalized = normalize_public_payment_columns(df)
		cleaned = clean_public_payment_data(normalized)

		self.assertEqual(len(cleaned), 1)
		self.assertFalse(cleaned.loc[0, "has_value_bucket_data"])

	def test_payment_terms_changed_flag_handles_boolean_and_free_text(self):
		self.assertEqual(normalize_payment_terms_changed_flag("No"), "No")
		self.assertEqual(normalize_payment_terms_changed_flag("True"), "Yes")
		self.assertEqual(normalize_payment_terms_changed_flag("No changes were made"), "No")
		self.assertEqual(normalize_payment_terms_changed_flag("Terms changed during COVID"), "Yes")
		self.assertEqual(normalize_payment_terms_changed_flag(pd.NA), "Unknown")

	def test_payment_terms_change_features_are_stable_model_inputs(self):
		df = pd.DataFrame(
			[
				{"payment_terms_have_changed": "No"},
				{"payment_terms_have_changed": "Terms changed during COVID for suppliers"},
				{"payment_terms_have_changed": pd.NA},
			]
		)

		result = add_payment_terms_change_features(df)

		self.assertEqual(result.loc[0, "payment_terms_changed_flag"], "No")
		self.assertEqual(result.loc[0, "payment_terms_changed_covid_related"], 0)
		self.assertEqual(result.loc[1, "payment_terms_changed_flag"], "Yes")
		self.assertEqual(result.loc[1, "payment_terms_changed_covid_related"], 1)
		self.assertEqual(result.loc[1, "payment_terms_changed_policy_related"], 1)
		self.assertEqual(result.loc[1, "payment_terms_changed_supplier_related"], 1)
		self.assertEqual(result.loc[2, "payment_terms_changed_flag"], "Unknown")

	def test_process_public_payment_csv_writes_outputs(self):
		csv_content = (
			"Report Id,Policy Regime,Start date,End date,Filing date,Company,Company number,"
			"Average time to pay,% Invoices paid within 30 days,% Invoices paid between 31 and 60 days,"
			"% Invoices paid later than 60 days,% Invoices not paid within agreed terms,"
			"Total value invoices paid within 30 days,Total value invoices paid between 31 and 60 days,"
			"Total value invoices paid later than 60 days,Total value invoices paid later than agreed terms,"
			"Standard payment terms,Payment terms have changed,E-Invoicing offered,Supply-chain financing offered,URL\n"
			"1,Regime-1,2020-01-01,2020-06-30,2020-07-01,Acme Limited,123,45,60,30,10,20,"
			"100,50,25,10,30 days,No,True,False,https://example.com\n"
		)

		with tempfile.TemporaryDirectory() as temp_dir:
			input_path = Path(temp_dir) / "raw.csv"
			output_dir = Path(temp_dir) / "processed"
			input_path.write_text(csv_content, encoding="utf-8")

			result = process_public_payment_csv(input_path, output_dir)

			self.assertEqual(result["ml_ready_rows"], 1)
			self.assertTrue((output_dir / "public_payment_cleaned.csv").exists())
			self.assertTrue((output_dir / "public_payment_flagged_rows.csv").exists())
			self.assertTrue((output_dir / "public_payment_ml_ready.csv").exists())
			self.assertTrue((output_dir / "public_payment_quality_report.json").exists())

			ml_ready = pd.read_csv(output_dir / "public_payment_ml_ready.csv")
			self.assertIn("payment_terms_have_changed", ml_ready.columns)
			self.assertIn("payment_terms_changed_flag", ml_ready.columns)
			self.assertEqual(ml_ready.loc[0, "payment_terms_changed_flag"], "No")


if __name__ == "__main__":
	unittest.main()

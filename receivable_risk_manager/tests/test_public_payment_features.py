import unittest

import pandas as pd

from receivable_risk_manager.ml.public_payment_features import (
	assign_public_payment_risk_band,
	build_company_payment_features,
	calculate_reported_paid_invoice_value,
)


class TestPublicPaymentFeatures(unittest.TestCase):
	def test_reported_paid_invoice_value_calculation(self):
		row = {
			"value_paid_within_30": 100,
			"value_paid_31_60": 50,
			"value_paid_later_60": 25,
		}

		self.assertEqual(calculate_reported_paid_invoice_value(row), 175)

	def test_reported_paid_invoice_value_missing_bucket_returns_na(self):
		row = {
			"value_paid_within_30": 100,
			"value_paid_31_60": pd.NA,
			"value_paid_later_60": 25,
		}

		self.assertTrue(pd.isna(calculate_reported_paid_invoice_value(row)))

	def test_public_payment_risk_band(self):
		self.assertEqual(assign_public_payment_risk_band({"avg_days_to_pay": 70}), "High")
		self.assertEqual(
			assign_public_payment_risk_band(
				{"avg_days_to_pay": 20, "pct_not_paid_within_terms": 15}
			),
			"Medium",
		)
		self.assertEqual(
			assign_public_payment_risk_band(
				{"avg_days_to_pay": 20, "pct_not_paid_within_terms": 5}
			),
			"Low",
		)

	def test_build_company_payment_features(self):
		df = pd.DataFrame(
			[
				{
					"company_number": "00000001",
					"avg_days_to_pay": 20,
					"pct_not_paid_within_terms": 5,
					"value_paid_within_30": 100,
					"value_paid_31_60": 50,
					"value_paid_later_60": 25,
					"value_paid_later_than_terms": 10,
				}
			]
		)

		result = build_company_payment_features(df)

		self.assertEqual(result.loc[0, "reported_paid_invoice_value"], 175)
		self.assertEqual(result.loc[0, "public_payment_risk_band"], "Low")
		self.assertEqual(result.loc[0, "company_reporting_count"], 1)


if __name__ == "__main__":
	unittest.main()

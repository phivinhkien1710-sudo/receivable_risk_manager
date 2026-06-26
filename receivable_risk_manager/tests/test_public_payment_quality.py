import unittest

import pandas as pd

from receivable_risk_manager.ml.data_quality import (
	detect_invalid_average_payment_days,
	detect_invalid_percentages,
	generate_data_quality_report,
	validate_public_payment_data,
)


class TestPublicPaymentQuality(unittest.TestCase):
	def test_invalid_percentage_detection(self):
		df = pd.DataFrame(
			[
				{"pct_paid_within_30": 101, "pct_paid_31_60": 0, "pct_paid_later_60": 0},
				{"pct_paid_within_30": 50, "pct_paid_31_60": 25, "pct_paid_later_60": 25},
			]
		)

		result = detect_invalid_percentages(df)

		self.assertTrue(result.iloc[0])
		self.assertFalse(result.iloc[1])

	def test_unrealistic_average_payment_days_detection(self):
		df = pd.DataFrame([{"avg_days_to_pay": 366}, {"avg_days_to_pay": 60}])

		result = detect_invalid_average_payment_days(df)

		self.assertTrue(result.iloc[0])
		self.assertFalse(result.iloc[1])

	def test_quality_report_generation(self):
		df = pd.DataFrame(
			[
				{
					"company_name": "ACME",
					"company_number": "00000001",
					"reporting_period_start": "2020-01-01",
					"reporting_period_end": "2020-06-30",
					"avg_days_to_pay": 20,
					"pct_paid_within_30": 50,
					"pct_paid_31_60": 25,
					"pct_paid_later_60": 25,
				}
			]
		)
		issues = validate_public_payment_data(df)
		report = generate_data_quality_report(df, issues)

		self.assertEqual(report["row_count"], 1)
		self.assertIn("missing_required_fields", report["issue_counts"])


if __name__ == "__main__":
	unittest.main()

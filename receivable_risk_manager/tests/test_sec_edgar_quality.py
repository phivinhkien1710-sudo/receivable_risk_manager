import unittest

import pandas as pd

from receivable_risk_manager.ml.sec_edgar_quality import summarize_sec_financial_profiles


class TestSecEdgarQuality(unittest.TestCase):
	def test_summarize_sec_financial_profiles(self):
		df = pd.DataFrame(
			[
				{
					"cik": "0000000001",
					"entity_name": "A",
					"revenue": 100,
					"cash": 10,
					"assets_current": 50,
					"liabilities_current": 25,
					"assets": 100,
					"liabilities": 40,
					"net_income": 5,
					"current_ratio": 2,
					"net_margin": 0.05,
					"sic_description": "Software",
					"sec_financial_risk_band": "Low",
				},
				{
					"cik": "0000000002",
					"entity_name": None,
					"revenue": None,
					"cash": None,
					"assets_current": None,
					"liabilities_current": None,
					"assets": None,
					"liabilities": None,
					"net_income": None,
					"current_ratio": None,
					"net_margin": None,
					"sic_description": None,
					"sec_financial_risk_band": "Unknown",
				},
			]
		)

		summary = summarize_sec_financial_profiles(df)

		self.assertEqual(summary["total_companies"], 2)
		self.assertEqual(summary["unique_ciks"], 2)
		self.assertEqual(summary["missing_entity_name"], 1)
		self.assertEqual(summary["missing_core_fields"]["revenue"], 1)
		self.assertEqual(summary["companies_with_no_core_financials"], 1)
		self.assertEqual(summary["risk_band_distribution"]["Low"], 1)
		self.assertEqual(summary["risk_band_distribution"]["Unknown"], 1)


if __name__ == "__main__":
	unittest.main()

import unittest

from receivable_risk_manager.ml.sec_edgar_features import (
	assign_sec_financial_risk_band,
	build_sec_company_profile,
	choose_latest_fact,
	normalize_cik,
	safe_divide,
)


class TestSecEdgarFeatures(unittest.TestCase):
	def test_normalize_cik(self):
		self.assertEqual(normalize_cik(320193), "0000320193")
		self.assertEqual(normalize_cik("123"), "0000000123")

	def test_choose_latest_fact_prefers_latest_filed_date(self):
		facts = [
			{"val": 100, "filed": "2022-01-01", "end": "2021-12-31", "form": "10-K"},
			{"val": 200, "filed": "2023-01-01", "end": "2022-12-31", "form": "10-K"},
		]

		self.assertEqual(choose_latest_fact(facts)["val"], 200)

	def test_safe_divide(self):
		self.assertEqual(safe_divide(10, 2), 5)
		self.assertIsNone(safe_divide(10, 0))
		self.assertIsNone(safe_divide(None, 2))

	def test_build_sec_company_profile(self):
		companyfacts = {
			"cik": 123,
			"entityName": "Example Corp",
			"sic": "7372",
			"sicDescription": "Services-Prepackaged Software",
			"facts": {
				"us-gaap": {
					"Revenues": {
						"units": {
							"USD": [
								{"val": 1000, "filed": "2024-01-30", "end": "2023-12-31", "form": "10-K"}
							]
						}
					},
					"CashAndCashEquivalentsAtCarryingValue": {
						"units": {
							"USD": [
								{"val": 200, "filed": "2024-01-30", "end": "2023-12-31", "form": "10-K"}
							]
						}
					},
					"AssetsCurrent": {
						"units": {
							"USD": [
								{"val": 500, "filed": "2024-01-30", "end": "2023-12-31", "form": "10-K"}
							]
						}
					},
					"LiabilitiesCurrent": {
						"units": {
							"USD": [
								{"val": 250, "filed": "2024-01-30", "end": "2023-12-31", "form": "10-K"}
							]
						}
					},
					"Assets": {
						"units": {
							"USD": [
								{"val": 2000, "filed": "2024-01-30", "end": "2023-12-31", "form": "10-K"}
							]
						}
					},
					"Liabilities": {
						"units": {
							"USD": [
								{"val": 900, "filed": "2024-01-30", "end": "2023-12-31", "form": "10-K"}
							]
						}
					},
					"NetIncomeLoss": {
						"units": {
							"USD": [
								{"val": 100, "filed": "2024-01-30", "end": "2023-12-31", "form": "10-K"}
							]
						}
					},
				}
			},
		}

		profile = build_sec_company_profile(companyfacts)

		self.assertEqual(profile["cik"], "0000000123")
		self.assertEqual(profile["entity_name"], "Example Corp")
		self.assertEqual(profile["revenue"], 1000)
		self.assertEqual(profile["current_ratio"], 2)
		self.assertEqual(profile["net_margin"], 0.1)
		self.assertEqual(profile["sec_financial_risk_band"], "Low")

	def test_assign_sec_financial_risk_band(self):
		self.assertEqual(
			assign_sec_financial_risk_band(
				{
					"current_ratio": 0.8,
					"cash_to_current_liabilities": 0.05,
					"liabilities_to_assets": 0.95,
					"net_margin": -0.2,
				}
			),
			"High",
		)
		self.assertEqual(assign_sec_financial_risk_band({"current_ratio": 1.2}), "Low")
		self.assertEqual(assign_sec_financial_risk_band({}), "Unknown")


if __name__ == "__main__":
	unittest.main()

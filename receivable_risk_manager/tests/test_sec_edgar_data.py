import json
import tempfile
import unittest
from pathlib import Path

from receivable_risk_manager.ml.sec_edgar_data import build_sec_financial_profiles, process_sec_companyfacts


class TestSecEdgarData(unittest.TestCase):
	def test_process_single_companyfacts_json(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			input_path = Path(temp_dir) / "CIK0000000123.json"
			output_path = Path(temp_dir) / "profiles.csv"
			input_path.write_text(json.dumps(build_sample_companyfacts()), encoding="utf-8")

			summary = process_sec_companyfacts(input_path, output_path)

			self.assertEqual(summary["companies_processed"], 1)
			self.assertTrue(output_path.exists())

	def test_build_sec_financial_profiles_from_directory(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			input_path = Path(temp_dir) / "CIK0000000123.json"
			input_path.write_text(json.dumps(build_sample_companyfacts()), encoding="utf-8")

			profiles = build_sec_financial_profiles(temp_dir)

			self.assertEqual(len(profiles), 1)
			self.assertEqual(profiles.loc[0, "cik"], "0000000123")
			self.assertIn("sec_financial_risk_band", profiles.columns)


def build_sample_companyfacts():
	return {
		"cik": 123,
		"entityName": "Example Corp",
		"facts": {
			"us-gaap": {
				"Revenues": {
					"units": {
						"USD": [{"val": 1000, "filed": "2024-01-30", "end": "2023-12-31", "form": "10-K"}]
					}
				},
				"AssetsCurrent": {
					"units": {
						"USD": [{"val": 500, "filed": "2024-01-30", "end": "2023-12-31", "form": "10-K"}]
					}
				},
				"LiabilitiesCurrent": {
					"units": {
						"USD": [{"val": 250, "filed": "2024-01-30", "end": "2023-12-31", "form": "10-K"}]
					}
				},
			}
		},
	}


if __name__ == "__main__":
	unittest.main()

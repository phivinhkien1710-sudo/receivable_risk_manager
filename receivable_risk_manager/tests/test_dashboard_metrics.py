import unittest

from receivable_risk_manager.services.dashboard_metrics import (
	fill_missing_levels,
	get_aging_bucket,
)


class TestDashboardMetrics(unittest.TestCase):
	def test_get_aging_bucket_boundaries(self):
		self.assertEqual(get_aging_bucket(None), "Current")
		self.assertEqual(get_aging_bucket(0), "Current")
		self.assertEqual(get_aging_bucket(1), "1-30")
		self.assertEqual(get_aging_bucket(30), "1-30")
		self.assertEqual(get_aging_bucket(31), "31-60")
		self.assertEqual(get_aging_bucket(60), "31-60")
		self.assertEqual(get_aging_bucket(61), "61-90")
		self.assertEqual(get_aging_bucket(90), "61-90")
		self.assertEqual(get_aging_bucket(91), "90+")

	def test_get_aging_bucket_handles_invalid_values(self):
		self.assertEqual(get_aging_bucket("not-a-number"), "Current")

	def test_fill_missing_levels_keeps_dashboard_chart_stable(self):
		rows = [
			{"risk_level": "High", "customer_count": 2},
		]

		result = fill_missing_levels(rows, "customer_count")

		self.assertEqual(
			result,
			[
				{"risk_level": "Low", "customer_count": 0},
				{"risk_level": "Medium", "customer_count": 0},
				{"risk_level": "High", "customer_count": 2},
			],
		)


if __name__ == "__main__":
	unittest.main()

import unittest

from receivable_risk_manager.services.risk_scoring import (
	calculate_customer_risk,
	calculate_invoice_risk,
	get_risk_level,
)


class TestRiskLevel(unittest.TestCase):
	def test_get_risk_level_boundaries(self):
		self.assertEqual(get_risk_level(0), "Low")
		self.assertEqual(get_risk_level(39), "Low")
		self.assertEqual(get_risk_level(40), "Medium")
		self.assertEqual(get_risk_level(69), "Medium")
		self.assertEqual(get_risk_level(70), "High")
		self.assertEqual(get_risk_level(100), "High")


class TestCustomerRiskScoring(unittest.TestCase):
	def test_low_risk_customer(self):
		result = calculate_customer_risk(
			{
				"total_invoices": 10,
				"closed_invoice_count": 10,
				"open_invoice_count": 0,
				"total_invoice_amount": 10000,
				"open_amount": 0,
				"average_payment_delay": 1,
				"late_payment_rate": 5,
			}
		)

		self.assertEqual(result["risk_score"], 0)
		self.assertEqual(result["risk_level"], "Low")
		self.assertEqual(result["risk_confidence"], "High")

	def test_medium_risk_customer_with_late_payments_and_open_exposure(self):
		result = calculate_customer_risk(
			{
				"total_invoices": 10,
				"closed_invoice_count": 8,
				"open_invoice_count": 3,
				"total_invoice_amount": 10000,
				"open_amount": 4000,
				"average_payment_delay": 8,
				"late_payment_rate": 35,
			}
		)

		self.assertEqual(result["risk_score"], 52)
		self.assertEqual(result["risk_level"], "Medium")
		self.assertIn("Late payment rate", result["risk_explanation"])
		self.assertIn("open invoices", result["risk_explanation"])

	def test_high_risk_customer(self):
		result = calculate_customer_risk(
			{
				"total_invoices": 100,
				"closed_invoice_count": 80,
				"open_invoice_count": 10,
				"total_invoice_amount": 100000,
				"open_amount": 60000,
				"average_payment_delay": 20,
				"late_payment_rate": 60,
			}
		)

		self.assertEqual(result["risk_score"], 80)
		self.assertEqual(result["risk_level"], "High")
		self.assertEqual(result["risk_confidence"], "High")

	def test_low_confidence_customer_explanation(self):
		result = calculate_customer_risk(
			{
				"total_invoices": 2,
				"closed_invoice_count": 2,
				"open_invoice_count": 0,
				"total_invoice_amount": 2000,
				"open_amount": 0,
				"average_payment_delay": 20,
				"late_payment_rate": 60,
			}
		)

		self.assertEqual(result["risk_score"], 25)
		self.assertEqual(result["risk_confidence"], "Low")
		self.assertIn("confidence is low", result["risk_explanation"])

	def test_customer_risk_score_never_exceeds_100(self):
		result = calculate_customer_risk(
			{
				"total_invoices": 100,
				"closed_invoice_count": 100,
				"open_invoice_count": 100,
				"total_invoice_amount": 100000,
				"open_amount": 1000000,
				"average_payment_delay": 999,
				"late_payment_rate": 100,
			}
		)

		self.assertLessEqual(result["risk_score"], 100)

	def test_customer_risk_explanation_is_not_empty(self):
		result = calculate_customer_risk({})

		self.assertTrue(result["risk_explanation"])


class TestInvoiceRiskScoring(unittest.TestCase):
	def test_low_risk_invoice_not_overdue(self):
		result = calculate_invoice_risk(
			{
				"days_overdue": 0,
				"invoice_amount": 100,
				"average_invoice_amount": 100,
				"customer_risk_level": "Low",
			}
		)

		self.assertEqual(result["risk_score"], 0)
		self.assertEqual(result["risk_level"], "Low")
		self.assertEqual(result["suggested_action"], "Monitor")

	def test_medium_risk_invoice_with_medium_customer_and_overdue_days(self):
		result = calculate_invoice_risk(
			{
				"days_overdue": 35,
				"invoice_amount": 100,
				"average_invoice_amount": 100,
				"customer_risk_level": "Medium",
			}
		)

		self.assertEqual(result["risk_score"], 40)
		self.assertEqual(result["risk_level"], "Medium")
		self.assertEqual(result["suggested_action"], "Send Reminder")

	def test_high_risk_invoice_with_high_customer_and_overdue_more_than_30_days(self):
		result = calculate_invoice_risk(
			{
				"days_overdue": 61,
				"invoice_amount": 200,
				"average_invoice_amount": 100,
				"customer_risk_level": "High",
			}
		)

		self.assertEqual(result["risk_score"], 75)
		self.assertEqual(result["risk_level"], "High")
		self.assertEqual(result["suggested_action"], "Escalate Collection")

	def test_high_value_invoice_compared_to_average_invoice_amount(self):
		result = calculate_invoice_risk(
			{
				"days_overdue": 0,
				"invoice_amount": 400,
				"average_invoice_amount": 100,
				"customer_risk_level": "Low",
			}
		)

		self.assertEqual(result["risk_score"], 15)
		self.assertIn("more than three times", result["explanation"])

	def test_suggested_action_matches_risk_level(self):
		medium_result = calculate_invoice_risk(
			{
				"days_overdue": 35,
				"invoice_amount": 100,
				"average_invoice_amount": 100,
				"customer_risk_level": "Medium",
			}
		)
		high_result = calculate_invoice_risk(
			{
				"days_overdue": 35,
				"invoice_amount": 600,
				"average_invoice_amount": 100,
				"customer_risk_level": "High",
			}
		)

		self.assertEqual(medium_result["risk_level"], "Medium")
		self.assertEqual(medium_result["suggested_action"], "Send Reminder")
		self.assertEqual(high_result["risk_level"], "High")
		self.assertEqual(high_result["suggested_action"], "Escalate Collection")

	def test_invoice_risk_score_never_exceeds_100(self):
		result = calculate_invoice_risk(
			{
				"days_overdue": 999,
				"invoice_amount": 1000000,
				"average_invoice_amount": 1,
				"customer_risk_level": "High",
			}
		)

		self.assertLessEqual(result["risk_score"], 100)


if __name__ == "__main__":
	unittest.main()

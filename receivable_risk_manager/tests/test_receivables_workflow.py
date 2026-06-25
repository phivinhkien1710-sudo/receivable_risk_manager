import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from receivable_risk_manager.services.collection_actions import (
	generate_collection_action_for_assessment,
)
from receivable_risk_manager.services.customer_risk import recalculate_customer_risk
from receivable_risk_manager.services.invoice_risk import recalculate_invoice_risk_assessment


class TestReceivablesWorkflow(FrappeTestCase):
	def setUp(self):
		self.test_prefix = "TEST-RRM-WORKFLOW"
		self.customer_id = f"{self.test_prefix}-CUSTOMER"
		self.invoice_id = f"{self.test_prefix}-INVOICE"
		self.cleanup_test_records()

	def tearDown(self):
		self.cleanup_test_records()

	def test_customer_invoice_action_workflow_and_active_duplicate_rule(self):
		customer = self.create_customer()
		invoice = self.create_open_invoice(customer)

		customer_risk = recalculate_customer_risk(customer.name)
		self.assertEqual(customer_risk["risk_level"], "High")

		assessment_result = recalculate_invoice_risk_assessment(
			invoice.name,
			analysis_date="2020-05-22",
		)
		self.assertIn(assessment_result["status"], {"created", "updated"})
		self.assertEqual(assessment_result["risk_level"], "High")

		first_action = generate_collection_action_for_assessment(
			assessment_result["assessment"],
			analysis_date="2020-05-22",
		)
		self.assertEqual(first_action["status"], "created")

		duplicate_action = generate_collection_action_for_assessment(
			assessment_result["assessment"],
			analysis_date="2020-05-22",
		)
		self.assertEqual(duplicate_action["status"], "skipped")

		action_doc = frappe.get_doc("Collection Action", first_action["collection_action"])
		action_doc.status = "Resolved"
		action_doc.save(ignore_permissions=True)

		new_action_after_resolution = generate_collection_action_for_assessment(
			assessment_result["assessment"],
			analysis_date="2020-05-22",
		)
		self.assertEqual(new_action_after_resolution["status"], "created")

		audit_logs = frappe.get_all(
			"Risk Audit Log",
			filters={"customer_id": self.customer_id},
			fields=["name"],
		)
		self.assertTrue(audit_logs)

	def create_customer(self):
		customer = frappe.new_doc("Receivables Customer")
		customer.customer_id = self.customer_id
		customer.customer_name = "Test RRM Customer"
		customer.total_invoices = 20
		customer.closed_invoice_count = 10
		customer.open_invoice_count = 10
		customer.total_invoice_amount = 100000
		customer.open_amount = 60000
		customer.average_payment_delay = 20
		customer.late_payment_rate = 60
		customer.risk_score = 0
		customer.risk_level = "Low"
		customer.risk_last_calculated_on = now_datetime()
		customer.insert(ignore_permissions=True)
		return customer

	def create_open_invoice(self, customer):
		invoice = frappe.new_doc("Receivables Invoice")
		invoice.invoice_id = self.invoice_id
		invoice.receivables_customer = customer.name
		invoice.customer_id = self.customer_id
		invoice.customer_name = customer.customer_name
		invoice.posting_date = "2020-03-01"
		invoice.due_date = "2020-03-15"
		invoice.invoice_amount = 50000
		invoice.is_open = 1
		invoice.days_overdue = 68
		invoice.status = "Overdue"
		invoice.late_payment_status = "Unknown"
		invoice.insert(ignore_permissions=True)
		return invoice

	def cleanup_test_records(self):
		for doctype in (
			"Collection Action",
			"Invoice Risk Assessment",
			"Receivables Invoice",
			"Receivables Customer",
			"Risk Audit Log",
		):
			for row in frappe.get_all(
				doctype,
				filters={"customer_id": ["like", f"{self.test_prefix}%"]},
				fields=["name"],
			):
				frappe.delete_doc(doctype, row.name, force=True, ignore_permissions=True)

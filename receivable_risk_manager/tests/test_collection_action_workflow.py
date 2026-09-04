import frappe
from frappe.model.workflow import WorkflowPermissionError
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from receivable_risk_manager.services.collection_action_workflow import (
	setup_collection_action_workflow,
)


class TestCollectionActionWorkflow(FrappeTestCase):
	def setUp(self):
		setup_collection_action_workflow()
		self.test_prefix = "TEST-RRM-CA-WORKFLOW"
		self.customer_id = f"{self.test_prefix}-CUSTOMER"
		self.customer = self.create_customer()

	def tearDown(self):
		for row in frappe.get_all(
			"Collection Action",
			filters={"customer_id": self.customer_id},
			fields=["name"],
		):
			frappe.delete_doc("Collection Action", row.name, force=True, ignore_permissions=True)

		for row in frappe.get_all(
			"Risk Audit Log",
			filters={"customer_id": self.customer_id},
			fields=["name"],
		):
			frappe.delete_doc("Risk Audit Log", row.name, force=True, ignore_permissions=True)

		frappe.delete_doc("Receivables Customer", self.customer.name, force=True, ignore_permissions=True)

	def test_valid_transition_is_allowed(self):
		action = self.create_action()

		action.status = "Contacted"
		action.save(ignore_permissions=True)

		self.assertEqual(action.status, "Contacted")

	def test_invalid_transition_is_rejected(self):
		action = self.create_action()

		action.status = "Promised to Pay"

		with self.assertRaises(WorkflowPermissionError):
			action.save(ignore_permissions=True)

	def test_proposed_action_can_be_approved(self):
		action = self.create_action(status="Proposed")

		action.status = "Open"
		action.save(ignore_permissions=True)

		self.assertEqual(action.status, "Open")
		self.assertTrue(
			frappe.get_all(
				"Risk Audit Log",
				filters={
					"reference_doctype": "Collection Action",
					"reference_name": action.name,
					"source": "Manual Review",
				},
			)
		)

	def test_proposed_action_can_be_rejected(self):
		action = self.create_action(status="Proposed")

		action.status = "Rejected"
		action.save(ignore_permissions=True)

		self.assertEqual(action.status, "Rejected")

	def test_rejected_action_does_not_block_new_action(self):
		from receivable_risk_manager.services.collection_actions import collection_action_exists

		external_invoice_id = f"{self.test_prefix}-INVOICE"
		action = self.create_action(status="Proposed", external_invoice_id=external_invoice_id)

		self.assertTrue(collection_action_exists(external_invoice_id, action.action_type))

		action.status = "Rejected"
		action.save(ignore_permissions=True)

		self.assertFalse(collection_action_exists(external_invoice_id, action.action_type))

	def create_customer(self):
		customer = frappe.new_doc("Receivables Customer")
		customer.customer_id = self.customer_id
		customer.customer_name = "Test RRM Workflow Customer"
		customer.total_invoices = 1
		customer.closed_invoice_count = 0
		customer.open_invoice_count = 1
		customer.total_invoice_amount = 1000
		customer.open_amount = 1000
		customer.average_payment_delay = 0
		customer.late_payment_rate = 0
		customer.risk_score = 0
		customer.risk_level = "Low"
		customer.risk_last_calculated_on = now_datetime()
		customer.insert(ignore_permissions=True)
		return customer

	def create_action(self, status="Open", external_invoice_id=None):
		"""Create a Collection Action, always inserting at "Proposed" first since
		the workflow requires every new document to start at its first state, then
		transitioning to `status` if a different starting state was requested.
		"""

		action = frappe.new_doc("Collection Action")
		action.receivables_customer = self.customer.name
		action.customer_id = self.customer_id
		action.customer_name = self.customer.customer_name
		action.external_invoice_id = external_invoice_id
		action.action_type = "Send Reminder"
		action.priority = "Medium"
		action.status = "Proposed"
		action.insert(ignore_permissions=True)

		if status != "Proposed":
			action.status = status
			action.save(ignore_permissions=True)

		return action

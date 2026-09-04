import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from receivable_risk_manager.services.collection_action_workflow import (
	setup_collection_action_workflow,
)
from receivable_risk_manager.services.collection_actions import (
	collection_action_exists,
	get_analysis_date,
)
from receivable_risk_manager.services.follow_up import run_follow_up_check


# Single-hop-per-save transitions needed to reach each target status from "Proposed".
HOP_PATHS = {
	"Open": ["Open"],
	"Contacted": ["Open", "Contacted"],
	"Promised to Pay": ["Open", "Contacted", "Promised to Pay"],
}


class TestFollowUp(FrappeTestCase):
	def setUp(self):
		setup_collection_action_workflow()
		self.test_prefix = "TEST-RRM-FOLLOWUP"
		self.customer_id = f"{self.test_prefix}-CUSTOMER"
		self.customer = self.create_customer()
		self._invoice_counter = 0
		# Anchor on the same analysis_date the real pipeline uses (max posting_date
		# across all Receivables Invoice, not wall-clock today) - the site's seed
		# Collection Actions have due_dates set relative to that same anchor, so
		# using it here means run_follow_up_check() never mistakes real seed data
		# for stale (wall-clock today() is years past the seed dataset's dates).
		self.analysis_date = get_analysis_date()

	def tearDown(self):
		for row in frappe.get_all(
			"Collection Action", filters={"customer_id": self.customer_id}, fields=["name"]
		):
			frappe.delete_doc("Collection Action", row.name, force=True, ignore_permissions=True)

		for row in frappe.get_all(
			"Invoice Risk Assessment", filters={"customer_id": self.customer_id}, fields=["name"]
		):
			frappe.delete_doc("Invoice Risk Assessment", row.name, force=True, ignore_permissions=True)

		for row in frappe.get_all(
			"Receivables Invoice", filters={"customer_id": self.customer_id}, fields=["name"]
		):
			frappe.delete_doc("Receivables Invoice", row.name, force=True, ignore_permissions=True)

		for row in frappe.get_all(
			"Risk Audit Log", filters={"customer_id": self.customer_id}, fields=["name"]
		):
			frappe.delete_doc("Risk Audit Log", row.name, force=True, ignore_permissions=True)

		frappe.delete_doc("Receivables Customer", self.customer.name, force=True, ignore_permissions=True)

		# run_follow_up_check() commits internally (matching the existing pattern in
		# services/collection_actions.py), which breaks FrappeTestCase's per-test
		# rollback isolation - anything created before that commit becomes permanent,
		# so this cleanup must itself be committed rather than left to a rollback.
		frappe.db.commit()

	def test_stale_open_action_past_threshold_gets_escalated(self):
		action = self.create_stale_action(status="Open", days_past_due=5)

		summary = run_follow_up_check(analysis_date=self.analysis_date)

		self.assertEqual(summary["actions_escalated"], 1)
		self.assertTrue(collection_action_exists(action.external_invoice_id, "Escalate Collection"))
		self.assertTrue(
			frappe.get_all(
				"Risk Audit Log",
				filters={"external_invoice_id": action.external_invoice_id, "source": "Pipeline"},
			)
		)

	def test_action_not_yet_past_threshold_is_left_alone(self):
		self.create_stale_action(status="Open", days_past_due=0)

		summary = run_follow_up_check(analysis_date=self.analysis_date)

		self.assertEqual(summary["actions_checked"], 0)
		self.assertEqual(summary["actions_escalated"], 0)

	def test_promised_to_pay_action_is_never_flagged(self):
		self.create_stale_action(status="Promised to Pay", days_past_due=30)

		summary = run_follow_up_check(analysis_date=self.analysis_date)

		self.assertEqual(summary["actions_checked"], 0)
		self.assertEqual(summary["actions_escalated"], 0)

	def test_existing_active_escalation_prevents_duplicate(self):
		external_invoice_id = f"{self.test_prefix}-SHARED-INVOICE"
		assessment = self.create_assessment(external_invoice_id)

		self.create_stale_action(
			status="Open",
			days_past_due=10,
			external_invoice_id=external_invoice_id,
			assessment=assessment,
		)
		self.create_stale_action(
			action_type="Escalate Collection",
			status="Proposed",
			days_past_due=0,
			external_invoice_id=external_invoice_id,
			assessment=assessment,
		)

		summary = run_follow_up_check(analysis_date=self.analysis_date)

		self.assertEqual(summary["actions_escalated"], 0)
		self.assertEqual(summary["actions_skipped_already_escalated"], 1)

	def test_top_of_ladder_escalate_action_is_skipped(self):
		self.create_stale_action(action_type="Escalate Collection", status="Open", days_past_due=10)

		summary = run_follow_up_check(analysis_date=self.analysis_date)

		self.assertEqual(summary["actions_escalated"], 0)
		self.assertEqual(summary["actions_skipped_top_of_ladder"], 1)

	def create_customer(self):
		customer = frappe.new_doc("Receivables Customer")
		customer.customer_id = self.customer_id
		customer.customer_name = "Test RRM Follow-up Customer"
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

	def create_invoice(self, external_invoice_id):
		invoice = frappe.new_doc("Receivables Invoice")
		invoice.invoice_id = external_invoice_id
		invoice.receivables_customer = self.customer.name
		invoice.customer_id = self.customer_id
		invoice.customer_name = self.customer.customer_name
		invoice.posting_date = "2020-03-01"
		invoice.due_date = "2020-03-15"
		invoice.invoice_amount = 50000
		invoice.is_open = 1
		invoice.days_overdue = 68
		invoice.status = "Overdue"
		invoice.late_payment_status = "Unknown"
		invoice.insert(ignore_permissions=True)
		return invoice

	def create_assessment(self, external_invoice_id):
		invoice = self.create_invoice(external_invoice_id)

		assessment = frappe.new_doc("Invoice Risk Assessment")
		assessment.receivables_customer = self.customer.name
		assessment.receivables_invoice = invoice.name
		assessment.external_invoice_id = external_invoice_id
		assessment.customer_id = self.customer_id
		assessment.customer_name = self.customer.customer_name
		assessment.risk_score = 85
		assessment.risk_level = "High"
		assessment.days_overdue = 68
		assessment.is_open = 1
		assessment.insert(ignore_permissions=True)
		return assessment

	def create_stale_action(
		self,
		action_type="Send Reminder",
		status="Open",
		days_past_due=5,
		external_invoice_id=None,
		assessment=None,
	):
		if external_invoice_id is None:
			self._invoice_counter += 1
			external_invoice_id = f"{self.test_prefix}-INVOICE-{self._invoice_counter}"

		if assessment is None:
			assessment = self.create_assessment(external_invoice_id)

		action = frappe.new_doc("Collection Action")
		action.receivables_customer = self.customer.name
		action.receivables_invoice = assessment.receivables_invoice
		action.invoice_risk_assessment = assessment.name
		action.external_invoice_id = external_invoice_id
		action.customer_id = self.customer_id
		action.customer_name = self.customer.customer_name
		action.action_type = action_type
		action.priority = "Medium"
		action.due_date = add_days(self.analysis_date, -days_past_due)
		action.status = "Proposed"
		action.insert(ignore_permissions=True)

		self.hop_to(action, status)
		action.reload()
		return action

	def hop_to(self, action, target_status):
		if target_status == "Proposed":
			return action

		for state in HOP_PATHS[target_status]:
			if action.status == state:
				continue
			action.status = state
			action.save(ignore_permissions=True)

		return action

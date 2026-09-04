from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from receivable_risk_manager.services.ai_agent import (
	draft_ai_recommendation,
	generate_ai_drafts_for_proposed_actions,
)


class TestAiAgent(FrappeTestCase):
	def setUp(self):
		self.test_prefix = "TEST-RRM-AI-AGENT"
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

	def test_skips_when_claude_cli_not_available(self):
		action = self.create_proposed_action()

		with patch("receivable_risk_manager.services.ai_agent._claude_cli_available", return_value=False):
			result = draft_ai_recommendation(action.name)

		self.assertEqual(result["status"], "skipped")

		action.reload()
		self.assertFalse(action.ai_drafted_on)

	def test_successful_draft_populates_fields_and_logs_event(self):
		action = self.create_proposed_action()
		drafted = {
			"recommendation_summary": "Customer is high risk, send a firm reminder today.",
			"drafted_message": "Dear customer, your invoice is overdue. Please pay immediately.",
		}

		with patch(
			"receivable_risk_manager.services.ai_agent._claude_cli_available", return_value=True
		), patch("receivable_risk_manager.services.ai_agent._call_claude", return_value=drafted):
			result = draft_ai_recommendation(action.name)

		self.assertEqual(result["status"], "drafted")

		action.reload()
		self.assertEqual(action.ai_recommendation_summary, drafted["recommendation_summary"])
		self.assertEqual(action.ai_drafted_message, drafted["drafted_message"])
		self.assertTrue(action.ai_drafted_on)

		self.assertTrue(
			frappe.get_all(
				"Risk Audit Log",
				filters={
					"reference_doctype": "Collection Action",
					"reference_name": action.name,
					"source": "AI Agent",
				},
			)
		)

	def test_failed_call_is_recorded_and_does_not_raise(self):
		action = self.create_proposed_action()

		with patch(
			"receivable_risk_manager.services.ai_agent._claude_cli_available", return_value=True
		), patch("receivable_risk_manager.services.ai_agent._call_claude", side_effect=Exception("boom")):
			result = draft_ai_recommendation(action.name)

		self.assertEqual(result["status"], "failed")

		action.reload()
		self.assertFalse(action.ai_drafted_on)
		self.assertTrue(action.ai_draft_error)

	def test_batch_entrypoint_only_drafts_undrafted_proposed_actions(self):
		# Not scoped to actions_found == 1: the entrypoint scans every Proposed action
		# site-wide by design, so other Proposed rows may legitimately exist already.
		action = self.create_proposed_action()

		with patch(
			"receivable_risk_manager.services.ai_agent._claude_cli_available", return_value=True
		), patch(
			"receivable_risk_manager.services.ai_agent._call_claude",
			return_value={"recommendation_summary": "s", "drafted_message": "m"},
		):
			summary = generate_ai_drafts_for_proposed_actions()

		self.assertGreaterEqual(summary["actions_found"], 1)
		self.assertGreaterEqual(summary["actions_drafted"], 1)
		self.assertEqual(summary["actions_failed"], 0)

		action.reload()
		self.assertTrue(action.ai_drafted_on)

	def create_customer(self):
		customer = frappe.new_doc("Receivables Customer")
		customer.customer_id = self.customer_id
		customer.customer_name = "Test RRM AI Agent Customer"
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

	def create_proposed_action(self):
		action = frappe.new_doc("Collection Action")
		action.receivables_customer = self.customer.name
		action.customer_id = self.customer_id
		action.customer_name = self.customer.customer_name
		action.external_invoice_id = f"{self.test_prefix}-INVOICE"
		action.action_type = "Send Reminder"
		action.priority = "Medium"
		action.status = "Proposed"
		action.insert(ignore_permissions=True)
		return action

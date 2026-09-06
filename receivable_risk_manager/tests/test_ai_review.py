"""Tests for the AI review reconciliation guardrail.

These are plain unittest cases with no Frappe site dependency: `reconcile` and
`action_severity` are pure functions precisely so the rules-as-floor policy can
be tested exhaustively without a database or a CLI call. That policy is the
riskiest thing in this app — it is what stops an LLM quietly deciding an overdue
invoice needs no chasing — so it gets tested directly rather than through an
integration path that would need Claude to be reachable.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from receivable_risk_manager.services.ai_review import (
	NO_ACTION,
	_apply_verdict,
	action_severity,
	reconcile,
)


MIN_CONFIDENCE = 0.7

RULE_ESCALATE = {
	"action_type": "Escalate Collection",
	"priority": "High",
	"due_date": "2020-05-22",
	"notes": "High-risk invoice INV-1 is 45 days overdue.",
}
RULE_REMINDER = {
	"action_type": "Send Reminder",
	"priority": "Medium",
	"due_date": "2020-05-25",
	"notes": "Medium-risk invoice INV-1.",
}


def verdict(action, confidence=0.9, priority="High", reasoning="because"):
	return {
		"external_invoice_id": "INV-1",
		"recommended_action": action,
		"priority": priority,
		"reasoning": reasoning,
		"confidence": confidence,
	}


class TestActionSeverity(unittest.TestCase):
	def test_ladder_is_ordered(self):
		self.assertLess(action_severity(NO_ACTION), action_severity("Send Reminder"))
		self.assertLess(action_severity("Send Reminder"), action_severity("Immediate Follow-up"))
		self.assertLess(action_severity("Immediate Follow-up"), action_severity("Escalate Collection"))

	def test_unknown_action_sorts_as_no_action(self):
		"""An unrecognised model response must never outrank the rule engine."""

		self.assertEqual(action_severity("Deploy Lawyers"), 0)
		self.assertEqual(action_severity(None), 0)


class TestReconcile(unittest.TestCase):
	def test_ai_escalating_above_rules_is_used_directly(self):
		final, meta = reconcile(RULE_REMINDER, verdict("Escalate Collection"), MIN_CONFIDENCE)

		self.assertEqual(final["action_type"], "Escalate Collection")
		self.assertEqual(meta["outcome"], "ai_escalated")
		self.assertEqual(meta["agreed"], 0)
		self.assertIn("because", final["notes"])

	def test_ai_softening_below_rules_keeps_the_rule_action(self):
		"""The core safety property: Claude cannot talk the system down."""

		final, meta = reconcile(RULE_ESCALATE, verdict(NO_ACTION), MIN_CONFIDENCE)

		self.assertEqual(final["action_type"], "Escalate Collection")
		self.assertEqual(meta["outcome"], "ai_softened_overridden")
		self.assertEqual(meta["agreed"], 0)
		self.assertEqual(meta["ai_proposed_action"], NO_ACTION)
		self.assertIn("AI review argued for No Action", final["notes"])

	def test_agreement_keeps_the_rule_action_and_is_flagged_agreed(self):
		final, meta = reconcile(RULE_ESCALATE, verdict("Escalate Collection"), MIN_CONFIDENCE)

		self.assertEqual(final["action_type"], "Escalate Collection")
		self.assertEqual(meta["outcome"], "agreed")
		self.assertEqual(meta["agreed"], 1)

	def test_low_confidence_falls_back_to_rules(self):
		final, meta = reconcile(RULE_REMINDER, verdict("Escalate Collection", confidence=0.4), MIN_CONFIDENCE)

		self.assertEqual(final["action_type"], "Send Reminder")
		self.assertEqual(meta["outcome"], "low_confidence")
		self.assertEqual(meta["ai_proposed_action"], "Escalate Collection")

	def test_low_confidence_cannot_soften_either(self):
		final, meta = reconcile(RULE_ESCALATE, verdict(NO_ACTION, confidence=0.1), MIN_CONFIDENCE)

		self.assertEqual(final["action_type"], "Escalate Collection")
		self.assertEqual(meta["outcome"], "low_confidence")

	def test_ai_catches_what_rules_missed(self):
		"""Rules say nothing is needed; Claude sees the customer context and disagrees."""

		final, meta = reconcile(None, verdict("Immediate Follow-up"), MIN_CONFIDENCE)

		self.assertIsNotNone(final)
		self.assertEqual(final["action_type"], "Immediate Follow-up")
		self.assertEqual(meta["outcome"], "ai_escalated")
		self.assertEqual(meta["agreed"], 0)

	def test_both_agree_nothing_is_needed(self):
		final, meta = reconcile(None, verdict(NO_ACTION), MIN_CONFIDENCE)

		self.assertIsNone(final)
		self.assertEqual(meta["agreed"], 1)

	def test_missing_verdict_falls_back_to_rules(self):
		"""A model that skipped this invoice must not silently drop the rule action."""

		final, meta = reconcile(RULE_ESCALATE, None, MIN_CONFIDENCE)

		self.assertEqual(final["action_type"], "Escalate Collection")
		self.assertEqual(meta["outcome"], "no_verdict")

	def test_unknown_ai_action_cannot_override_rules(self):
		final, meta = reconcile(RULE_ESCALATE, verdict("Deploy Lawyers"), MIN_CONFIDENCE)

		self.assertEqual(final["action_type"], "Escalate Collection")
		self.assertEqual(meta["outcome"], "ai_softened_overridden")


class TestCliResolution(unittest.TestCase):
	"""The bug that made the first UI-started run fail: a bench worker's PATH is
	stripped, so shutil.which alone finds nothing in exactly the process that
	needs the binary. resolve_cli_path is pure given a fake discover_fn."""

	def test_configured_absolute_path_wins_when_it_exists(self):
		from receivable_risk_manager.services.ai_review import resolve_cli_path

		# __file__ is guaranteed to be a real file on disk.
		self.assertEqual(
			resolve_cli_path(__file__, discover_fn=lambda: "/discovered/claude"),
			__file__,
		)

	def test_falls_back_to_discovery_when_configured_path_is_missing(self):
		from receivable_risk_manager.services.ai_review import resolve_cli_path

		self.assertEqual(
			resolve_cli_path("/nope/not/here", discover_fn=lambda: "/discovered/claude"),
			"/discovered/claude",
		)

	def test_falls_back_to_the_bare_name_so_subprocess_can_still_try_path(self):
		from receivable_risk_manager.services.ai_review import resolve_cli_path

		self.assertEqual(resolve_cli_path("claude", discover_fn=lambda: None), "claude")

	def test_returns_none_when_nothing_is_configured_or_found(self):
		from receivable_risk_manager.services.ai_review import resolve_cli_path

		self.assertIsNone(resolve_cli_path("", discover_fn=lambda: None))

	def test_newest_extension_version_wins(self):
		from receivable_risk_manager.services.ai_review import (
			CLAUDE_EXTENSION_VERSION_RE,
			pick_newest_by_version,
		)

		paths = [
			"/ext/anthropic.claude-code-2.1.9/resources/native-binary/claude",
			"/ext/anthropic.claude-code-2.1.260/resources/native-binary/claude",
			"/ext/anthropic.claude-code-2.1.100/resources/native-binary/claude",
		]
		self.assertIn("2.1.260", pick_newest_by_version(paths, CLAUDE_EXTENSION_VERSION_RE))


class TestApplyVerdictOnExistingAction(FrappeTestCase):
	"""_apply_verdict() against an invoice that already has an active
	Collection Action -- the case reconcile()'s own unit tests can't cover,
	since they test the reconciliation policy in isolation, not what happens
	to the database record afterward.

	This is the fix for a real gap: a disagreement on an already-existing
	action used to be recorded only on Invoice Risk Assessment, which the
	Collection Action Queue's "Disagreements Only" filter never reads --
	invisible in the one place a reviewer would think to check. Confirmed
	against a real AI Review Run (AIRV-00006) on staging.local: 4 of 25
	disagreements were silently unsurfaced this way before this fix.
	"""

	def setUp(self):
		self.test_prefix = "TEST-RRM-APPLYVERDICT"
		self.customer_id = f"{self.test_prefix}-CUSTOMER"
		self.external_invoice_id = f"{self.test_prefix}-INVOICE-1"
		self.customer = self._create_customer()
		self.invoice = self._create_invoice()
		self.assessment = self._create_assessment()
		self.import_job = self._create_import_job()
		self.ai_review_run = self._create_ai_review_run()
		self.existing_action = self._create_existing_action()

	def tearDown(self):
		for dt in ("Collection Action", "Risk Audit Log", "Invoice Risk Assessment", "Receivables Invoice"):
			for row in frappe.get_all(dt, filters={"customer_id": self.customer_id}, fields=["name"]):
				frappe.delete_doc(dt, row.name, force=True, ignore_permissions=True)
		frappe.delete_doc("Receivables Customer", self.customer.name, force=True, ignore_permissions=True)
		frappe.delete_doc("AI Review Run", self.ai_review_run.name, force=True, ignore_permissions=True)
		frappe.delete_doc("Receivables Import Job", self.import_job.name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_disagreement_annotates_existing_action_without_changing_its_type(self):
		row = frappe._dict(
			{
				"assessment_name": self.assessment.name,
				"external_invoice_id": self.external_invoice_id,
				"customer_id": self.customer_id,
				"customer_name": "Test ApplyVerdict Co",
				"risk_score": 90,
			}
		)
		rule_action = {"action_type": "Escalate Collection", "priority": "High", "due_date": None, "notes": "rule"}
		final_action = dict(rule_action)  # softened-and-overridden case: floor kept as-is
		meta = {
			"ai_proposed_action": "Immediate Follow-up",
			"ai_reasoning": "Reliable customer, one anomalous invoice.",
			"ai_confidence": 0.76,
			"agreed": 0,
			"outcome": "ai_softened_overridden",
		}

		outcome = _apply_verdict(row, rule_action, final_action, meta, "TEST-RUN-1", frappe.utils.today())

		self.assertEqual(outcome, "already_exists")
		self.assertEqual(
			frappe.db.count("Collection Action", {"customer_id": self.customer_id}),
			1,
			"a disagreement on an existing action must never create a second one",
		)

		refreshed = frappe.get_doc("Collection Action", self.existing_action.name)
		self.assertEqual(refreshed.action_type, "Escalate Collection", "AI review must never change an existing action's type")
		self.assertEqual(refreshed.ai_agreed_with_rules, 0)
		self.assertEqual(refreshed.ai_proposed_action, "Immediate Follow-up")
		self.assertEqual(refreshed.rule_proposed_action, "Escalate Collection")
		self.assertAlmostEqual(refreshed.ai_confidence, 0.76, places=2)

		self.assertTrue(
			frappe.get_all(
				"Risk Audit Log",
				filters={"external_invoice_id": self.external_invoice_id, "source": "AI Agent"},
			),
			"a disagreement on an existing action must leave an audit trail too",
		)

	def test_agreement_annotates_but_does_not_log_an_audit_event(self):
		row = frappe._dict(
			{
				"assessment_name": self.assessment.name,
				"external_invoice_id": self.external_invoice_id,
				"customer_id": self.customer_id,
				"customer_name": "Test ApplyVerdict Co",
				"risk_score": 90,
			}
		)
		rule_action = {"action_type": "Escalate Collection", "priority": "High", "due_date": None, "notes": "rule"}
		meta = {
			"ai_proposed_action": "Escalate Collection",
			"ai_reasoning": "Matches rule baseline.",
			"ai_confidence": 0.95,
			"agreed": 1,
			"outcome": "agreed",
		}

		_apply_verdict(row, rule_action, rule_action, meta, "TEST-RUN-1", frappe.utils.today())

		refreshed = frappe.get_doc("Collection Action", self.existing_action.name)
		self.assertEqual(refreshed.ai_agreed_with_rules, 1)
		self.assertFalse(
			frappe.get_all("Risk Audit Log", filters={"external_invoice_id": self.external_invoice_id, "source": "AI Agent"}),
			"a plain agreement shouldn't clutter the audit trail the way a disagreement does",
		)

	def test_new_action_keeps_the_batch_used_for_the_review(self):
		frappe.delete_doc("Collection Action", self.existing_action.name, force=True, ignore_permissions=True)
		row = frappe._dict(
			{
				"assessment_name": self.assessment.name,
				"external_invoice_id": self.external_invoice_id,
				"customer_id": self.customer_id,
				"customer_name": "Test ApplyVerdict Co",
				"risk_score": 90,
			}
		)
		rule_action = {"action_type": "Send Reminder", "priority": "Medium", "due_date": None, "notes": "rule"}
		meta = {
			"ai_proposed_action": "Escalate Collection",
			"ai_reasoning": "Customer context requires escalation.",
			"ai_confidence": 0.9,
			"agreed": 0,
			"outcome": "ai_escalated",
		}
		final_action = {
			"action_type": "Escalate Collection",
			"priority": "High",
			"due_date": None,
			"notes": "AI escalation",
		}

		outcome = _apply_verdict(
			row,
			rule_action,
			final_action,
			meta,
			self.ai_review_run.name,
			frappe.utils.today(),
			receivables_import_job=self.import_job.name,
		)

		self.assertEqual(outcome, "created")
		action = frappe.get_doc(
			"Collection Action",
			{"customer_id": self.customer_id, "action_type": "Escalate Collection"},
		)
		self.assertEqual(action.receivables_import_job, self.import_job.name)

	def _create_customer(self):
		customer = frappe.new_doc("Receivables Customer")
		customer.customer_id = self.customer_id
		customer.customer_name = "Test ApplyVerdict Co"
		customer.total_invoices = 1
		customer.open_invoice_count = 1
		customer.total_invoice_amount = 50000
		customer.open_amount = 50000
		customer.risk_score = 90
		customer.risk_level = "High"
		customer.risk_last_calculated_on = now_datetime()
		customer.insert(ignore_permissions=True)
		return customer

	def _create_invoice(self):
		invoice = frappe.new_doc("Receivables Invoice")
		invoice.invoice_id = self.external_invoice_id
		invoice.receivables_customer = self.customer.name
		invoice.customer_id = self.customer_id
		invoice.customer_name = "Test ApplyVerdict Co"
		invoice.posting_date = "2020-01-01"
		invoice.due_date = "2020-01-15"
		invoice.invoice_amount = 50000
		invoice.is_open = 1
		invoice.days_overdue = 66
		invoice.status = "Overdue"
		invoice.late_payment_status = "Unknown"
		invoice.insert(ignore_permissions=True)
		return invoice

	def _create_assessment(self):
		assessment = frappe.new_doc("Invoice Risk Assessment")
		assessment.receivables_customer = self.customer.name
		assessment.receivables_invoice = self.invoice.name
		assessment.external_invoice_id = self.external_invoice_id
		assessment.customer_id = self.customer_id
		assessment.customer_name = "Test ApplyVerdict Co"
		assessment.risk_score = 90
		assessment.risk_level = "High"
		assessment.days_overdue = 66
		assessment.is_open = 1
		assessment.insert(ignore_permissions=True)
		return assessment

	def _create_import_job(self):
		job = frappe.new_doc("Receivables Import Job")
		job.status = "Completed"
		job.csv_file = "/private/files/test-batch.csv"
		job.as_of_date = frappe.utils.today()
		job.insert(ignore_permissions=True)
		return job

	def _create_ai_review_run(self):
		run = frappe.new_doc("AI Review Run")
		run.receivables_import_job = self.import_job.name
		run.insert(ignore_permissions=True)
		return run

	def _create_existing_action(self):
		action = frappe.new_doc("Collection Action")
		action.receivables_customer = self.customer.name
		action.receivables_invoice = self.invoice.name
		action.invoice_risk_assessment = self.assessment.name
		action.external_invoice_id = self.external_invoice_id
		action.customer_id = self.customer_id
		action.customer_name = "Test ApplyVerdict Co"
		action.action_type = "Escalate Collection"
		action.priority = "High"
		action.due_date = frappe.utils.today()
		action.status = "Proposed"
		action.insert(ignore_permissions=True)
		action.status = "Open"
		action.save(ignore_permissions=True)
		return action


class TestRunAiReviewStaleBatch(FrappeTestCase):
	"""run_ai_review() against an Import Batch whose invoices were already
	wiped -- the exact trap demo_reset.sh creates for any older batch once a
	newer reset has run: the Receivables Import Job record survives (kept
	for audit history) but every Receivables Batch Member it referenced is
	gone. Confirmed against real data on staging.local: AIRV-00007, scoped to
	a batch a later reset had wiped, returned assessments_in_scope: 0 with no
	explanation -- indistinguishable from "genuinely nothing new to review."
	"""

	def setUp(self):
		self.job = frappe.new_doc("Receivables Import Job")
		self.job.status = "Completed"
		self.job.csv_file = "/private/files/does-not-need-to-exist-for-this-test.csv"
		self.job.as_of_date = frappe.utils.today()
		self.job.insert(ignore_permissions=True)
		frappe.db.commit()

	def tearDown(self):
		frappe.db.delete("AI Review Run", {"receivables_import_job": self.job.name})
		frappe.delete_doc("Receivables Import Job", self.job.name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_stale_batch_with_zero_members_gets_a_clear_message(self):
		from receivable_risk_manager.services.ai_review import run_ai_review

		run = frappe.new_doc("AI Review Run")
		run.receivables_import_job = self.job.name
		run.run_trigger = "Manual"
		run.insert(ignore_permissions=True)
		frappe.db.commit()

		with patch("receivable_risk_manager.services.ai_review.claude_cli_available", return_value=True):
			result = run_ai_review(run.name)

		self.assertEqual(result["status"], "Completed")
		self.assertEqual(result["reason"], "stale_batch")

		refreshed = frappe.get_doc("AI Review Run", run.name)
		self.assertEqual(refreshed.status, "Completed")
		self.assertIn("no live invoices", refreshed.error_summary)
		self.assertIn(self.job.name, refreshed.error_summary)

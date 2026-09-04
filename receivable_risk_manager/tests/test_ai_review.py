"""Tests for the AI review reconciliation guardrail.

These are plain unittest cases with no Frappe site dependency: `reconcile` and
`action_severity` are pure functions precisely so the rules-as-floor policy can
be tested exhaustively without a database or a CLI call. That policy is the
riskiest thing in this app — it is what stops an LLM quietly deciding an overdue
invoice needs no chasing — so it gets tested directly rather than through an
integration path that would need Claude to be reachable.
"""

import unittest

from receivable_risk_manager.services.ai_review import (
	NO_ACTION,
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

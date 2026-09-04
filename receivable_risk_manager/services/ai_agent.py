import json
import shutil
import subprocess
from pathlib import Path

import frappe
from frappe.utils import now_datetime

from receivable_risk_manager.services.risk_audit import log_collection_action_event


ACTION_DOCTYPE = "Collection Action"
ASSESSMENT_DOCTYPE = "Invoice Risk Assessment"
AUDIT_DOCTYPE = "Risk Audit Log"

CLAUDE_BINARY = "claude"
CLAUDE_MODEL = "haiku"
REQUEST_TIMEOUT = 60
HISTORY_LIMIT = 5

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "collection_action_instructions.md"

RESPONSE_SCHEMA = {
	"type": "object",
	"properties": {
		"recommendation_summary": {"type": "string"},
		"drafted_message": {"type": "string"},
	},
	"required": ["recommendation_summary", "drafted_message"],
}

_system_prompt_cache = None


def _get_system_prompt():
	global _system_prompt_cache
	if _system_prompt_cache is None:
		_system_prompt_cache = SYSTEM_PROMPT_PATH.read_text()
	return _system_prompt_cache


def _claude_cli_available():
	return shutil.which(CLAUDE_BINARY) is not None


def draft_ai_recommendation(action_name):
	"""Draft an AI recommendation + reminder message for one Proposed Collection Action.

	Never raises - a missing CLI or a failed call is recorded on the document and
	returned as a status so the caller (a batch pipeline step) can keep going.
	"""

	action_doc = frappe.get_doc(ACTION_DOCTYPE, action_name)

	if not _claude_cli_available():
		return {
			"collection_action": action_name,
			"status": "skipped",
			"reason": "Claude Code CLI not found on PATH (run `claude login` on this host).",
		}

	try:
		assessment_doc = (
			frappe.get_doc(ASSESSMENT_DOCTYPE, action_doc.invoice_risk_assessment)
			if action_doc.invoice_risk_assessment
			else None
		)
		history = _get_history(action_doc)
		prompt = _build_prompt(action_doc, assessment_doc, history)
		drafted = _call_claude(prompt)

		action_doc.db_set("ai_recommendation_summary", drafted["recommendation_summary"])
		action_doc.db_set("ai_drafted_message", drafted["drafted_message"])
		action_doc.db_set("ai_drafted_on", now_datetime())
		action_doc.db_set("ai_draft_error", "")

		log_collection_action_event(
			collection_action_name=action_doc.name,
			reason="AI draft generated: recommendation and reminder message ready for review.",
			source="AI Agent",
			customer_id=action_doc.customer_id,
			external_invoice_id=action_doc.external_invoice_id,
		)

		return {
			"collection_action": action_name,
			"status": "drafted",
		}
	except Exception:
		error = frappe.get_traceback()
		frappe.log_error(
			title=f"AI draft generation failed: {action_name}",
			message=error,
		)
		action_doc.db_set("ai_draft_error", error[:140])
		return {
			"collection_action": action_name,
			"status": "failed",
			"error": error,
		}


def generate_ai_drafts_for_proposed_actions():
	"""Draft AI recommendations for every Proposed action that doesn't have one yet."""

	summary = {
		"actions_found": 0,
		"actions_drafted": 0,
		"actions_skipped_no_cli": 0,
		"actions_failed": 0,
		"errors": [],
	}

	actions = frappe.get_all(
		ACTION_DOCTYPE,
		filters={"status": "Proposed", "ai_drafted_on": ["is", "not set"]},
		fields=["name"],
		order_by="creation asc",
	)

	for row in actions:
		summary["actions_found"] += 1

		try:
			result = draft_ai_recommendation(row.name)
		except Exception:
			result = {"status": "failed", "error": frappe.get_traceback()}

		if result["status"] == "drafted":
			summary["actions_drafted"] += 1
		elif result["status"] == "skipped":
			summary["actions_skipped_no_cli"] += 1
		else:
			summary["actions_failed"] += 1
			summary["errors"].append({"collection_action": row.name, "error": result.get("error")})

	return summary


def _get_history(action_doc):
	if not action_doc.external_invoice_id:
		return {"actions": [], "audit_events": []}

	prior_actions = frappe.get_all(
		ACTION_DOCTYPE,
		filters={
			"external_invoice_id": action_doc.external_invoice_id,
			"name": ["!=", action_doc.name],
		},
		fields=["action_type", "status", "creation"],
		order_by="creation desc",
		limit_page_length=HISTORY_LIMIT,
	)

	audit_events = frappe.get_all(
		AUDIT_DOCTYPE,
		filters={"external_invoice_id": action_doc.external_invoice_id},
		fields=["reason", "source", "calculated_on"],
		order_by="calculated_on desc",
		limit_page_length=HISTORY_LIMIT,
	)

	return {"actions": prior_actions, "audit_events": audit_events}


def _build_prompt(action_doc, assessment_doc, history):
	facts = {
		"customer_name": action_doc.customer_name,
		"external_invoice_id": action_doc.external_invoice_id,
		"action_type": action_doc.action_type,
		"priority": action_doc.priority,
		"due_date": str(action_doc.due_date) if action_doc.due_date else None,
		"risk_score": assessment_doc.risk_score if assessment_doc else action_doc.created_from_risk_score,
		"risk_level": assessment_doc.risk_level if assessment_doc else None,
		"days_overdue": assessment_doc.days_overdue if assessment_doc else None,
		"risk_explanation": assessment_doc.explanation if assessment_doc else None,
		"suggested_action": assessment_doc.suggested_action if assessment_doc else None,
		"prior_collection_actions": [
			f"{row.action_type} ({row.status}) on {row.creation}" for row in history["actions"]
		],
		"prior_audit_events": [
			f"[{row.source}] {row.reason} ({row.calculated_on})" for row in history["audit_events"]
		],
	}

	return json.dumps(facts, indent=2, default=str)


def _call_claude(prompt):
	"""Run the Claude Code CLI headlessly, authenticated via the logged-in Claude
	subscription session on this host (no API key involved). Tools are disabled
	since this call only needs to produce text, and --json-schema constrains the
	model to the exact shape we need.
	"""

	completed = subprocess.run(
		[
			CLAUDE_BINARY,
			"-p",
			"--model",
			CLAUDE_MODEL,
			"--output-format",
			"json",
			"--tools",
			"",
			"--system-prompt",
			_get_system_prompt(),
			"--json-schema",
			json.dumps(RESPONSE_SCHEMA),
			prompt,
		],
		capture_output=True,
		text=True,
		timeout=REQUEST_TIMEOUT,
	)

	if completed.returncode != 0:
		frappe.throw(f"Claude Code CLI exited with status {completed.returncode}: {completed.stderr[:500]}")

	envelope = json.loads(completed.stdout)

	if envelope.get("is_error"):
		frappe.throw(f"Claude Code CLI returned an error: {envelope.get('result')}")

	drafted = envelope.get("structured_output")
	if drafted is None:
		drafted = json.loads(envelope["result"])

	if "recommendation_summary" not in drafted or "drafted_message" not in drafted:
		frappe.throw("Claude Code response missing required keys.")

	return drafted

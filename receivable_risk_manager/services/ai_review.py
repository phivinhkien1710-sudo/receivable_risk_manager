"""Claude reviews open invoice risk assessments and proposes collection actions.

This is deliberately a different job from services/ai_agent.py. `ai_agent`
writes the customer-facing message for an action the rule engine already
decided on. `ai_review` decides *what action to propose in the first place* —
reading the invoice, the customer's payment history, and the rule engine's own
recommendation, then either backing that recommendation, raising it, or arguing
for no action at all.

The rule engine is a floor, not a peer. Claude may propose something more
severe than the rules and that proposal is used directly. If Claude proposes
something *less* severe, the rule engine's action is created anyway and the
disagreement is recorded on it for a human to adjudicate. An LLM never silently
suppresses a risk the deterministic rules flagged — in a credit-control tool
the cost of a missed escalation is real money, and the cost of an unnecessary
one is a human spending ten seconds rejecting it.
"""

import glob
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import frappe
from frappe.utils import cint, flt, getdate, now_datetime

from receivable_risk_manager.services.collection_actions import (
	ACTION_DOCTYPE,
	ASSESSMENT_DOCTYPE,
	get_action_from_assessment,
	get_active_collection_action_name,
	get_active_invoice_key,
	get_analysis_date,
)
from receivable_risk_manager.services.risk_audit import log_collection_action_event


RUN_DOCTYPE = "AI Review Run"
BATCH_MEMBER_DOCTYPE = "Receivables Batch Member"
CUSTOMER_DOCTYPE = "Receivables Customer"

CLAUDE_BINARY = "claude"
# Matches the version in the Claude Code VS Code extension's install directory,
# e.g. ".../anthropic.claude-code-2.1.212/resources/native-binary/claude".
CLAUDE_EXTENSION_VERSION_RE = re.compile(r"claude-code-(\d+\.\d+\.\d+)")
DEFAULT_MODEL = "haiku"
DEFAULT_CHUNK_SIZE = 25
DEFAULT_MIN_CONFIDENCE = 0.7
REQUEST_TIMEOUT = 180
MAX_CONSECUTIVE_CHUNK_FAILURES = 3
COMMIT_EVERY = 200

NO_ACTION = "No Action"

# Severity ladder. Index is the comparison key: Claude may move an invoice up
# this list on its own authority, never down.
ACTION_LADDER = [
	NO_ACTION,
	"Send Reminder",
	"Immediate Follow-up",
	"Escalate Collection",
]

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "invoice_review_instructions.md"

RESPONSE_SCHEMA = {
	"type": "object",
	"properties": {
		"verdicts": {
			"type": "array",
			"items": {
				"type": "object",
				"properties": {
					"external_invoice_id": {"type": "string"},
					"recommended_action": {"type": "string", "enum": ACTION_LADDER},
					"priority": {"type": "string", "enum": ["Low", "Medium", "High"]},
					"reasoning": {"type": "string"},
					"confidence": {"type": "number"},
				},
				"required": [
					"external_invoice_id",
					"recommended_action",
					"priority",
					"reasoning",
					"confidence",
				],
			},
		}
	},
	"required": ["verdicts"],
}

_system_prompt_cache = None


def _get_system_prompt():
	global _system_prompt_cache
	if _system_prompt_cache is None:
		_system_prompt_cache = SYSTEM_PROMPT_PATH.read_text()
	return _system_prompt_cache


def pick_newest_by_version(paths, version_re):
	"""Pure: of several candidate binaries, pick the highest embedded version.
	Paths with no version match sort last."""

	if not paths:
		return None

	def version_key(path):
		match = version_re.search(path)
		return tuple(int(part) for part in match.group(1).split(".")) if match else (-1,)

	return max(paths, key=version_key)


def discover_claude_cli():
	"""Locate a `claude` binary the operator already has.

	`shutil.which` alone is not enough: a bench worker is spawned with a
	stripped PATH that does not include Homebrew or a user's shell profile, so
	a CLI that works fine in an interactive terminal is invisible to the
	background job that actually needs it. This was not hypothetical — the
	first AI Review Run started from the Desk UI failed instantly for exactly
	this reason while the same code worked from a console.

	The Claude Code VS Code extension bundles its own binary off-PATH, so check
	there too. Same approach as lead_outreach_manager's discover_claude_cli.
	"""

	candidates = []
	for base in ("~/.vscode/extensions", "~/.vscode-server/extensions"):
		pattern = os.path.join(
			os.path.expanduser(base),
			"anthropic.claude-code-*",
			"resources",
			"native-binary",
			"claude",
		)
		candidates.extend(path for path in glob.glob(pattern) if os.path.isfile(path))

	return pick_newest_by_version(candidates, CLAUDE_EXTENSION_VERSION_RE) or shutil.which(
		CLAUDE_BINARY
	)


def resolve_cli_path(configured_path, discover_fn=discover_claude_cli):
	"""A configured absolute path wins if it is a real file; otherwise
	auto-detect; otherwise fall back to the configured string itself so a bare
	command name still gets tried via the subprocess's own PATH lookup."""

	if configured_path and os.path.isfile(configured_path):
		return configured_path

	discovered = discover_fn()
	return discovered or (configured_path or None)


def get_claude_cli_path():
	"""The binary this app should invoke, honouring the Risk Settings override."""

	configured = (frappe.db.get_single_value("Risk Settings", "ai_review_cli_path") or "").strip()
	return resolve_cli_path(configured)


def claude_cli_available():
	return get_claude_cli_path() is not None


def action_severity(action_type):
	"""Position on the severity ladder. Unknown action types sort as No Action
	so an unrecognised model response can never outrank the rule engine."""

	if not action_type:
		return 0

	try:
		return ACTION_LADDER.index(action_type)
	except ValueError:
		return 0


def get_review_settings():
	"""Read AI review knobs off Risk Settings, each with a safe fallback."""

	settings = frappe.get_single("Risk Settings")

	chunk_size = cint(getattr(settings, "ai_review_chunk_size", 0)) or DEFAULT_CHUNK_SIZE
	min_confidence = flt(getattr(settings, "ai_min_confidence", 0)) or DEFAULT_MIN_CONFIDENCE
	model = (getattr(settings, "ai_review_model", "") or "").strip() or DEFAULT_MODEL

	return {
		"chunk_size": max(1, chunk_size),
		"min_confidence": min_confidence,
		"model": model,
	}


def get_eligible_assessments(receivables_import_job=None, limit=None, run_name=None):
	"""Open, unreviewed-by-this-run assessments, optionally scoped to one batch.

	Batch scoping joins through Receivables Batch Member rather than reading a
	field off the assessment, so an invoice that arrived in an older batch and
	was merely *updated* by a newer one still counts as a member of both.
	"""

	conditions = ["assessment.is_open = 1"]
	values = {}

	if run_name:
		conditions.append(
			"(assessment.last_ai_review_run IS NULL OR assessment.last_ai_review_run != %(run_name)s)"
		)
		values["run_name"] = run_name

	join = ""
	if receivables_import_job:
		join = f"""
			INNER JOIN `tab{BATCH_MEMBER_DOCTYPE}` member
				ON member.external_invoice_id = assessment.external_invoice_id
			   AND member.receivables_import_job = %(import_job)s
		"""
		values["import_job"] = receivables_import_job

	limit_clause = ""
	if limit:
		limit_clause = "LIMIT %(limit)s"
		values["limit"] = cint(limit)

	return frappe.db.sql(
		f"""
		SELECT DISTINCT
			assessment.name AS assessment_name,
			assessment.external_invoice_id AS external_invoice_id,
			assessment.customer_id AS customer_id,
			assessment.customer_name AS customer_name,
			assessment.risk_score AS risk_score,
			assessment.risk_level AS risk_level,
			assessment.days_overdue AS days_overdue,
			assessment.invoice_amount AS invoice_amount,
			assessment.due_date AS due_date,
			assessment.explanation AS explanation,
			assessment.customer_risk_level AS customer_risk_level
		FROM `tab{ASSESSMENT_DOCTYPE}` assessment
		{join}
		WHERE {" AND ".join(conditions)}
		ORDER BY assessment.risk_score DESC, assessment.days_overdue DESC, assessment.name ASC
		{limit_clause}
		""",
		values,
		as_dict=True,
	)


def _get_customer_context(customer_ids):
	"""Payment-history context per customer, fetched once per chunk."""

	if not customer_ids:
		return {}

	rows = frappe.get_all(
		CUSTOMER_DOCTYPE,
		filters={"customer_id": ["in", list(customer_ids)]},
		fields=[
			"customer_id",
			"total_invoices",
			"open_invoice_count",
			"open_amount",
			"average_payment_delay",
			"late_payment_rate",
			"risk_level",
			"risk_score",
		],
	)

	return {row.customer_id: row for row in rows}


def build_chunk_payload(rows, analysis_date):
	"""One JSON payload describing a chunk of invoices for Claude to review.

	Each row carries the rule engine's own recommendation, so the model is
	explicitly reacting to a baseline rather than guessing in a vacuum.
	"""

	customer_context = _get_customer_context({row.customer_id for row in rows if row.customer_id})
	invoices = []

	for row in rows:
		rule_action = get_action_from_assessment(
			frappe._dict(
				{
					"external_invoice_id": row.external_invoice_id,
					"days_overdue": row.days_overdue,
					"risk_level": row.risk_level,
				}
			),
			analysis_date,
		)
		customer = customer_context.get(row.customer_id) or {}

		invoices.append(
			{
				"external_invoice_id": row.external_invoice_id,
				"customer_name": row.customer_name,
				"invoice_amount": flt(row.invoice_amount),
				"days_overdue": cint(row.days_overdue),
				"due_date": str(row.due_date) if row.due_date else None,
				"invoice_risk_score": flt(row.risk_score),
				"invoice_risk_level": row.risk_level,
				"rule_explanation": row.explanation,
				"rule_recommended_action": rule_action["action_type"] if rule_action else NO_ACTION,
				"customer_risk_level": customer.get("risk_level") or row.customer_risk_level,
				"customer_risk_score": flt(customer.get("risk_score")),
				"customer_total_invoices": cint(customer.get("total_invoices")),
				"customer_open_invoices": cint(customer.get("open_invoice_count")),
				"customer_open_amount": flt(customer.get("open_amount")),
				"customer_average_payment_delay_days": flt(customer.get("average_payment_delay")),
				"customer_late_payment_rate": flt(customer.get("late_payment_rate")),
			}
		)

	return json.dumps({"analysis_date": str(analysis_date), "invoices": invoices}, indent=2, default=str)


def call_claude_for_chunk(payload, model):
	"""Run the Claude Code CLI headlessly for one chunk of invoices.

	Subscription-authenticated via the logged-in session on this host, no API
	key. Tools are disabled since this only needs to return structured text.
	"""

	binary = get_claude_cli_path() or CLAUDE_BINARY

	completed = subprocess.run(
		[
			binary,
			"-p",
			"--model",
			model,
			"--output-format",
			"json",
			"--tools",
			"",
			"--system-prompt",
			_get_system_prompt(),
			"--json-schema",
			json.dumps(RESPONSE_SCHEMA),
			payload,
		],
		capture_output=True,
		text=True,
		timeout=REQUEST_TIMEOUT,
	)

	if completed.returncode != 0:
		raise RuntimeError(
			f"Claude Code CLI exited with status {completed.returncode}: {completed.stderr[:500]}"
		)

	envelope = json.loads(completed.stdout)

	if envelope.get("is_error"):
		raise RuntimeError(f"Claude Code CLI returned an error: {envelope.get('result')}")

	parsed = envelope.get("structured_output")
	if parsed is None:
		parsed = json.loads(envelope["result"])

	verdicts = parsed.get("verdicts")
	if not isinstance(verdicts, list):
		raise RuntimeError("Claude Code response did not contain a verdicts array.")

	return {v.get("external_invoice_id"): v for v in verdicts if v.get("external_invoice_id")}


def reconcile(rule_action, verdict, min_confidence):
	"""Decide the final proposal for one invoice from the rule floor and Claude's verdict.

	Returns (final_action | None, meta). `final_action` is None only when both
	the rules and Claude agree nothing is needed.
	"""

	rule_type = rule_action["action_type"] if rule_action else NO_ACTION

	if not verdict:
		return rule_action, {
			"ai_proposed_action": None,
			"ai_reasoning": None,
			"ai_confidence": 0.0,
			"agreed": 1,
			"outcome": "no_verdict",
		}

	ai_type = verdict.get("recommended_action") or NO_ACTION
	confidence = flt(verdict.get("confidence"))
	reasoning = (verdict.get("reasoning") or "").strip()

	meta = {
		"ai_proposed_action": ai_type,
		"ai_reasoning": reasoning,
		"ai_confidence": confidence,
	}

	# Low confidence: the rule engine decides, and we say so out loud.
	if confidence < min_confidence:
		meta.update({"agreed": 0 if ai_type != rule_type else 1, "outcome": "low_confidence"})
		return rule_action, meta

	# Claude wants to go harder than the rules: its call, used as-is.
	if action_severity(ai_type) > action_severity(rule_type):
		meta.update({"agreed": 0, "outcome": "ai_escalated"})
		return {
			"action_type": ai_type,
			"priority": verdict.get("priority") or "High",
			"due_date": rule_action["due_date"] if rule_action else None,
			"notes": f"Proposed by AI review (above rule baseline {rule_type}): {reasoning}",
		}, meta

	# Claude wants to go softer than the rules: rules win, disagreement recorded.
	if action_severity(ai_type) < action_severity(rule_type):
		meta.update({"agreed": 0, "outcome": "ai_softened_overridden"})
		softened = dict(rule_action)
		softened["notes"] = (
			f"{rule_action['notes']}\n\n"
			f"AI review argued for {ai_type} instead, but the rule baseline was kept "
			f"for a human to adjudicate. AI reasoning: {reasoning}"
		)
		return softened, meta

	# Same rung of the ladder.
	meta.update({"agreed": 1, "outcome": "agreed"})
	if rule_action:
		return rule_action, meta

	return None, meta


def _apply_verdict(
	row,
	rule_action,
	final_action,
	meta,
	run_name,
	analysis_date,
	receivables_import_job=None,
):
	"""Persist one reviewed assessment and create its Collection Action, if any."""

	frappe.db.set_value(
		ASSESSMENT_DOCTYPE,
		row.assessment_name,
		{
			"last_ai_review_run": run_name,
			"ai_recommended_action": meta.get("ai_proposed_action"),
			"ai_reasoning": meta.get("ai_reasoning"),
			"ai_confidence": meta.get("ai_confidence"),
		},
		update_modified=False,
	)

	if not final_action:
		return "no_action"

	existing_name = get_active_collection_action_name(row.external_invoice_id, final_action["action_type"])
	if existing_name:
		# The invoice already has an active action, so nothing new gets
		# created -- but the verdict still needs to be visible somewhere a
		# human will actually look. Without this, a disagreement on an
		# already-existing action was recorded only on Invoice Risk
		# Assessment, which the Collection Action Queue's "Disagreements
		# Only" filter never reads -- so it was invisible in the one place
		# a reviewer would think to check. Annotates the existing record
		# with the same AI fields a newly-created one gets; deliberately
		# never touches its action_type/priority/status, since AI review
		# only ever informs an existing action, never silently changes what
		# a human is already looking at.
		frappe.db.set_value(
			ACTION_DOCTYPE,
			existing_name,
			{
				"rule_proposed_action": rule_action["action_type"] if rule_action else NO_ACTION,
				"ai_proposed_action": meta.get("ai_proposed_action"),
				"ai_reasoning": meta.get("ai_reasoning"),
				"ai_confidence": meta.get("ai_confidence"),
				"ai_agreed_with_rules": meta.get("agreed", 1),
				"ai_review_run": run_name,
			},
			update_modified=False,
		)
		if not meta.get("agreed", 1):
			log_collection_action_event(
				collection_action_name=existing_name,
				reason=(
					f"AI review re-examined this existing action and disagreed: "
					f"proposed {meta.get('ai_proposed_action')} vs the current "
					f"{final_action['action_type']}. {meta.get('ai_reasoning') or ''}"
				),
				source="AI Agent",
				customer_id=row.customer_id,
				external_invoice_id=row.external_invoice_id,
			)
		return "already_exists"

	doc = frappe.new_doc(ACTION_DOCTYPE)
	doc.update(
		{
			"receivables_customer": frappe.db.get_value(
				ASSESSMENT_DOCTYPE, row.assessment_name, "receivables_customer"
			),
			"receivables_invoice": frappe.db.get_value(
				ASSESSMENT_DOCTYPE, row.assessment_name, "receivables_invoice"
			),
			"invoice_risk_assessment": row.assessment_name,
			"external_invoice_id": row.external_invoice_id,
			"customer_id": row.customer_id,
			"customer_name": row.customer_name,
			"action_type": final_action["action_type"],
			"priority": final_action["priority"],
			"status": "Proposed",
			"due_date": final_action.get("due_date") or analysis_date,
			"notes": final_action.get("notes"),
			"auto_generated": 1,
			"active_invoice_key": get_active_invoice_key(
				row.external_invoice_id, final_action["action_type"]
			),
			"created_from_risk_score": row.risk_score or 0,
			"last_updated_on": now_datetime(),
			"rule_proposed_action": rule_action["action_type"] if rule_action else NO_ACTION,
			"ai_proposed_action": meta.get("ai_proposed_action"),
			"ai_reasoning": meta.get("ai_reasoning"),
			"ai_confidence": meta.get("ai_confidence"),
			"ai_agreed_with_rules": meta.get("agreed", 1),
			"ai_review_run": run_name,
			"receivables_import_job": receivables_import_job,
		}
	)
	doc.save(ignore_permissions=True)

	log_collection_action_event(
		collection_action_name=doc.name,
		reason=(
			f"AI review proposed {final_action['action_type']} "
			f"(rule baseline: {rule_action['action_type'] if rule_action else NO_ACTION}, "
			f"outcome: {meta.get('outcome')})."
		),
		source="AI Agent",
		customer_id=row.customer_id,
		external_invoice_id=row.external_invoice_id,
	)

	return "created"


def run_ai_review(run_name):
	"""Execute one AI Review Run end to end. Never raises past the run record."""

	run = frappe.get_doc(RUN_DOCTYPE, run_name)
	settings = get_review_settings()
	analysis_date = get_analysis_date()

	run.db_set(
		{
			"status": "Running",
			"started_on": now_datetime(),
			"model_used": settings["model"],
			"chunk_size_used": settings["chunk_size"],
			"min_confidence_used": settings["min_confidence"],
			"error_summary": None,
		},
		update_modified=False,
	)

	if not claude_cli_available():
		run.db_set(
			{
				"status": "Failed",
				"completed_on": now_datetime(),
				"error_summary": (
					"Claude Code CLI could not be located. It was not on the background "
					"worker's PATH (which is stripped, and does not inherit your shell "
					"profile), and no bundled VS Code extension binary was found. Set an "
					"absolute path in Risk Settings > AI Review CLI Path."
				),
			},
			update_modified=False,
		)
		frappe.db.commit()
		return {"status": "Failed", "reason": "cli_unavailable"}

	rows = get_eligible_assessments(
		receivables_import_job=run.receivables_import_job,
		limit=run.limit_rows,
		run_name=run_name,
	)

	if run.receivables_import_job and not rows:
		# A batch-scoped run finding nothing is ambiguous on its own: either
		# there's genuinely nothing left to review, or the batch is a zombie --
		# a Receivables Import Job record that still exists (batches are kept
		# for audit history even after a reset) but whose invoices were
		# deleted by a later wipe, most commonly demo_reset.sh. Both looked
		# identical as a bare assessments_in_scope: 0 -- hit this for real
		# scoping a review at a batch a later demo reset had already wiped.
		# Distinguishing them here means the run record explains itself
		# instead of a human having to go query Receivables Batch Member by
		# hand to find out which case they're in.
		batch_member_count = frappe.db.count(
			"Receivables Batch Member", {"receivables_import_job": run.receivables_import_job}
		)
		if batch_member_count == 0:
			run.db_set(
				{
					"status": "Completed",
					"completed_on": now_datetime(),
					"assessments_in_scope": 0,
					"error_summary": (
						f"Import batch {run.receivables_import_job} has no live invoices. "
						"The batch record still exists for audit history, but its data was "
						"removed by a later reset (most likely a demo reset) after this batch "
						"was originally imported. Point this run at the current batch instead, "
						"or leave Import Batch blank to review across all open assessments."
					),
				},
				update_modified=False,
			)
			frappe.db.commit()
			return {"status": "Completed", "reason": "stale_batch", "assessments_in_scope": 0}

	counters = {
		"assessments_in_scope": len(rows),
		"assessments_reviewed": 0,
		"proposed_action": 0,
		"proposed_no_action": 0,
		"actions_created": 0,
		"actions_already_existed": 0,
		"agreed_with_rules": 0,
		"disagreed_with_rules": 0,
		"low_confidence_fallback": 0,
		"error_rows": 0,
		"chunks_total": 0,
		"chunks_failed": 0,
	}
	errors = []
	consecutive_failures = 0
	chunk_size = settings["chunk_size"]

	for start in range(0, len(rows), chunk_size):
		chunk = rows[start : start + chunk_size]
		counters["chunks_total"] += 1

		try:
			payload = build_chunk_payload(chunk, analysis_date)
			verdicts = call_claude_for_chunk(payload, settings["model"])
			consecutive_failures = 0
		except Exception:
			counters["chunks_failed"] += 1
			counters["error_rows"] += len(chunk)
			consecutive_failures += 1
			error = frappe.get_traceback()
			errors.append(error[:500])
			frappe.log_error(title=f"AI review chunk failed: {run_name}", message=error)

			if consecutive_failures >= MAX_CONSECUTIVE_CHUNK_FAILURES:
				run.db_set(
					{
						"status": "Failed",
						"completed_on": now_datetime(),
						"error_summary": (
							f"Aborted after {consecutive_failures} consecutive CLI failures. "
							f"Already-reviewed rows are saved; re-running this batch resumes where it stopped.\n\n"
							+ "\n\n".join(errors[-2:])
						),
						**counters,
					},
					update_modified=False,
				)
				frappe.db.commit()
				return {"status": "Failed", "reason": "consecutive_cli_failures", **counters}

			continue

		for row in chunk:
			try:
				rule_action = get_action_from_assessment(
					frappe._dict(
						{
							"external_invoice_id": row.external_invoice_id,
							"days_overdue": row.days_overdue,
							"risk_level": row.risk_level,
						}
					),
					analysis_date,
				)
				final_action, meta = reconcile(
					rule_action, verdicts.get(row.external_invoice_id), settings["min_confidence"]
				)
				outcome = _apply_verdict(
					row,
					rule_action,
					final_action,
					meta,
					run_name,
					analysis_date,
					receivables_import_job=run.receivables_import_job,
				)

				counters["assessments_reviewed"] += 1
				if final_action:
					counters["proposed_action"] += 1
				else:
					counters["proposed_no_action"] += 1
				if outcome == "created":
					counters["actions_created"] += 1
				elif outcome == "already_exists":
					counters["actions_already_existed"] += 1
				if meta.get("agreed"):
					counters["agreed_with_rules"] += 1
				else:
					counters["disagreed_with_rules"] += 1
				if meta.get("outcome") == "low_confidence":
					counters["low_confidence_fallback"] += 1

			except Exception:
				counters["error_rows"] += 1
				error = frappe.get_traceback()
				errors.append(error[:500])
				frappe.log_error(
					title=f"AI review row failed: {row.assessment_name}", message=error
				)

		if counters["assessments_reviewed"] % COMMIT_EVERY < chunk_size:
			frappe.db.commit()

	status = "Completed With Errors" if (counters["error_rows"] or counters["chunks_failed"]) else "Completed"
	run.db_set(
		{
			"status": status,
			"completed_on": now_datetime(),
			"error_summary": "\n\n".join(errors[-3:]) if errors else None,
			**counters,
		},
		update_modified=False,
	)
	frappe.db.commit()

	return {"status": status, **counters}


def queue_ai_review_run(run_name):
	"""Put one Draft run onto the long background queue."""

	run = frappe.get_doc(RUN_DOCTYPE, run_name)

	if run.status not in ("Draft", "Failed", "Completed With Errors"):
		frappe.throw(f"AI Review Run {run_name} is {run.status} and cannot be queued.")

	run.db_set({"status": "Queued"}, update_modified=False)
	frappe.db.commit()

	frappe.enqueue(
		"receivable_risk_manager.services.ai_review.run_ai_review",
		queue="long",
		timeout=7200,
		run_name=run_name,
	)

	return {"run": run_name, "status": "Queued"}

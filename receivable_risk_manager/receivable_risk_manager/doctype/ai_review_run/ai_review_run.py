import frappe
from frappe.model.document import Document


QUEUEABLE_STATUSES = ("Draft",)


class AIReviewRun(Document):
	"""One pass of Claude reviewing open invoice risk assessments and proposing
	collection actions.

	Exists so the AI has a visible unit of work. Before this doctype, drafting
	happened silently inside a daily cron over whatever happened to be Proposed,
	with no record of what was looked at, what changed, or where the AI and the
	rule engine disagreed. Mirrors Lead Outreach Manager's Candidate
	Classification Run: status-tracked, batch-scoped, chunked, resumable, and
	started by a human clicking a button rather than by a schedule.
	"""

	def validate(self):
		if self.limit_rows is not None and self.limit_rows < 0:
			frappe.throw("Limit Rows cannot be negative.")


@frappe.whitelist()
def start_ai_review_run(run_name):
	"""Queue one AI Review Run onto a background worker.

	Thin whitelisted wrapper: business logic lives in services/ai_review.py,
	matching this app's established controller-stays-thin convention.
	"""

	from receivable_risk_manager.services.ai_review import queue_ai_review_run

	return queue_ai_review_run(run_name)

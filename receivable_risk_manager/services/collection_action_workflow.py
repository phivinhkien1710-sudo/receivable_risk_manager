import frappe


DOCTYPE = "Collection Action"
WORKFLOW_NAME = "Collection Action Workflow"
WORKFLOW_STATE_FIELD = "status"

# Existing Select options on Collection Action.status - reused as workflow states
# instead of adding a separate workflow_state field, so every report/filter that
# already reads `status` keeps working unchanged.
STATES = [
	{"state": "Proposed", "allow_edit": "Accounts Manager"},
	{"state": "Open", "allow_edit": "Accounts User"},
	{"state": "Contacted", "allow_edit": "Accounts User"},
	{"state": "Promised to Pay", "allow_edit": "Accounts User"},
	{"state": "Escalated", "allow_edit": "Accounts Manager"},
	{"state": "Resolved", "allow_edit": "Accounts Manager"},
	{"state": "Rejected", "allow_edit": "Accounts Manager"},
]

# Routine day-to-day progress is left to Accounts User; escalating (raising the
# severity of a case) and reopening a resolved case require Accounts Manager,
# mirroring the sign-off most credit-control teams expect for those actions.
TRANSITIONS = [
	{"state": "Proposed", "action": "Approve", "next_state": "Open", "allowed": "Accounts Manager"},
	{"state": "Proposed", "action": "Reject", "next_state": "Rejected", "allowed": "Accounts Manager"},
	{"state": "Open", "action": "Mark as Contacted", "next_state": "Contacted", "allowed": "Accounts User"},
	{"state": "Open", "action": "Escalate", "next_state": "Escalated", "allowed": "Accounts Manager"},
	{"state": "Open", "action": "Resolve", "next_state": "Resolved", "allowed": "Accounts User"},
	{
		"state": "Contacted",
		"action": "Record Promise to Pay",
		"next_state": "Promised to Pay",
		"allowed": "Accounts User",
	},
	{"state": "Contacted", "action": "Escalate", "next_state": "Escalated", "allowed": "Accounts Manager"},
	{"state": "Contacted", "action": "Resolve", "next_state": "Resolved", "allowed": "Accounts User"},
	{
		"state": "Promised to Pay",
		"action": "Resolve",
		"next_state": "Resolved",
		"allowed": "Accounts User",
	},
	{
		"state": "Promised to Pay",
		"action": "Escalate",
		"next_state": "Escalated",
		"allowed": "Accounts Manager",
	},
	{
		"state": "Escalated",
		"action": "Resolve",
		"next_state": "Resolved",
		"allowed": "Accounts Manager",
	},
	{"state": "Resolved", "action": "Reopen", "next_state": "Open", "allowed": "Accounts Manager"},
]


def setup_collection_action_workflow():
	"""Create or update the Collection Action workflow (idempotent).

	Reuses the existing `status` Select field as the workflow state field, so
	the doctype schema and every existing filter/report on `status` are
	untouched. Safe to re-run: it edits the existing Workflow doc in place
	instead of failing on a duplicate insert.
	"""

	for state in STATES:
		_ensure_workflow_state(state["state"])

	for transition in TRANSITIONS:
		_ensure_workflow_action_master(transition["action"])

	if frappe.db.exists("Workflow", WORKFLOW_NAME):
		workflow = frappe.get_doc("Workflow", WORKFLOW_NAME)
		workflow.set("states", [])
		workflow.set("transitions", [])
	else:
		workflow = frappe.new_doc("Workflow")
		workflow.workflow_name = WORKFLOW_NAME
		workflow.document_type = DOCTYPE
		workflow.workflow_state_field = WORKFLOW_STATE_FIELD
		workflow.send_email_alert = 0

	workflow.is_active = 1

	for state in STATES:
		workflow.append(
			"states",
			{
				"state": state["state"],
				"doc_status": "0",
				"allow_edit": state["allow_edit"],
			},
		)

	for transition in TRANSITIONS:
		workflow.append(
			"transitions",
			{
				"state": transition["state"],
				"action": transition["action"],
				"next_state": transition["next_state"],
				"allowed": transition["allowed"],
			},
		)

	workflow.save(ignore_permissions=True)
	frappe.db.commit()

	return workflow.name


def _ensure_workflow_state(state_name):
	if frappe.db.exists("Workflow State", state_name):
		return

	frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state_name}).insert(
		ignore_permissions=True
	)


def _ensure_workflow_action_master(action_name):
	if frappe.db.exists("Workflow Action Master", action_name):
		return

	frappe.get_doc(
		{"doctype": "Workflow Action Master", "workflow_action_name": action_name}
	).insert(ignore_permissions=True)

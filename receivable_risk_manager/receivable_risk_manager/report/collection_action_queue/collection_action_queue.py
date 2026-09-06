import frappe
from frappe.utils import cint


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"label": "Collection Action",
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Collection Action",
			"width": 130,
		},
		{
			"label": "External Invoice ID",
			"fieldname": "external_invoice_id",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"label": "Customer ID",
			"fieldname": "customer_id",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": "Customer Name",
			"fieldname": "customer_name",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": "Action Type",
			"fieldname": "action_type",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": "Priority",
			"fieldname": "priority",
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"label": "Status",
			"fieldname": "status",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": "Due Date",
			"fieldname": "due_date",
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"label": "Risk Score",
			"fieldname": "created_from_risk_score",
			"fieldtype": "Int",
			"width": 100,
		},
		{
			"label": "Rule Said",
			"fieldname": "rule_proposed_action",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"label": "AI Said",
			"fieldname": "ai_proposed_action",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"label": "Agreed",
			"fieldname": "ai_agreed_with_rules",
			"fieldtype": "Check",
			"width": 70,
		},
		{
			"label": "AI Confidence",
			"fieldname": "ai_confidence",
			"fieldtype": "Float",
			"precision": "2",
			"width": 110,
		},
		{
			"label": "AI Reasoning",
			"fieldname": "ai_reasoning",
			"fieldtype": "Data",
			"width": 420,
		},
		{
			"label": "Notes",
			"fieldname": "notes",
			"fieldtype": "Data",
			"width": 300,
		},
	]


def get_data(filters):
	report_filters = build_report_filters(filters)

	return frappe.get_all(
		"Collection Action",
		filters=report_filters,
		fields=[
			"name",
			"external_invoice_id",
			"customer_id",
			"customer_name",
			"action_type",
			"priority",
			"status",
			"due_date",
			"created_from_risk_score",
			"rule_proposed_action",
			"ai_proposed_action",
			"ai_agreed_with_rules",
			"ai_confidence",
			"ai_reasoning",
			"notes",
		],
		order_by="due_date asc, created_from_risk_score desc",
	)


def build_report_filters(filters):
	report_filters = {}

	priority = clean_text(filters.get("priority"))
	if priority:
		report_filters["priority"] = priority

	status = clean_text(filters.get("status"))
	if status:
		report_filters["status"] = status
	else:
		report_filters["status"] = "Open"

	action_type = clean_text(filters.get("action_type"))
	if action_type:
		report_filters["action_type"] = action_type

	customer_id = clean_text(filters.get("customer_id"))
	if customer_id:
		report_filters["customer_id"] = customer_id

	receivables_import_job = clean_text(filters.get("receivables_import_job"))
	if receivables_import_job:
		report_filters["receivables_import_job"] = receivables_import_job

	ai_review_run = clean_text(filters.get("ai_review_run"))
	if ai_review_run:
		report_filters["ai_review_run"] = ai_review_run

	# The whole reason AI review is worth running: surface only the invoices
	# where Claude and the rule engine reached different conclusions.
	if cint(filters.get("disagreements_only")):
		report_filters["ai_agreed_with_rules"] = 0

	return report_filters


def clean_text(value):
	if value is None:
		return None

	value = str(value).strip()
	return value or None

import frappe


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
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
			"label": "Notes",
			"fieldname": "notes",
			"fieldtype": "Data",
			"width": 450,
		},
	]


def get_data(filters):
	report_filters = build_report_filters(filters)

	return frappe.get_all(
		"Collection Action",
		filters=report_filters,
		fields=[
			"external_invoice_id",
			"customer_id",
			"customer_name",
			"action_type",
			"priority",
			"status",
			"due_date",
			"created_from_risk_score",
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

	return report_filters


def clean_text(value):
	if value is None:
		return None

	value = str(value).strip()
	return value or None

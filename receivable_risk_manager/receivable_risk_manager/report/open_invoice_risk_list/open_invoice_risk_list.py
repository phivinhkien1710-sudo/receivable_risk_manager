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
			"label": "Due Date",
			"fieldname": "due_date",
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"label": "Days Overdue",
			"fieldname": "days_overdue",
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"label": "Invoice Amount",
			"fieldname": "invoice_amount",
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"label": "Customer Risk Score",
			"fieldname": "customer_risk_score",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": "Customer Risk Level",
			"fieldname": "customer_risk_level",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": "Invoice Risk Score",
			"fieldname": "risk_score",
			"fieldtype": "Int",
			"width": 130,
		},
		{
			"label": "Invoice Risk Level",
			"fieldname": "risk_level",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": "Suggested Action",
			"fieldname": "suggested_action",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": "Explanation",
			"fieldname": "explanation",
			"fieldtype": "Data",
			"width": 500,
		},
	]


def get_data(filters):
	report_filters = build_report_filters(filters)

	return frappe.get_all(
		"Invoice Risk Assessment",
		filters=report_filters,
		fields=[
			"external_invoice_id",
			"customer_id",
			"customer_name",
			"due_date",
			"days_overdue",
			"invoice_amount",
			"customer_risk_score",
			"customer_risk_level",
			"risk_score",
			"risk_level",
			"suggested_action",
			"explanation",
		],
		order_by="risk_score desc, days_overdue desc, invoice_amount desc",
	)


def build_report_filters(filters):
	report_filters = {}

	risk_level = filters.get("risk_level")
	if risk_level:
		report_filters["risk_level"] = risk_level
	else:
		report_filters["risk_level"] = ["in", ["Medium", "High"]]

	customer_id = clean_text(filters.get("customer_id"))
	if customer_id:
		report_filters["customer_id"] = customer_id

	min_days_overdue = to_number(filters.get("min_days_overdue"))
	if min_days_overdue is not None:
		report_filters["days_overdue"] = [">=", min_days_overdue]

	suggested_action = clean_text(filters.get("suggested_action"))
	if suggested_action:
		report_filters["suggested_action"] = suggested_action

	return report_filters


def clean_text(value):
	if value is None:
		return None
	value = str(value).strip()
	return value or None


def to_number(value):
	if value in (None, ""):
		return None

	try:
		return float(value)
	except (TypeError, ValueError):
		return None

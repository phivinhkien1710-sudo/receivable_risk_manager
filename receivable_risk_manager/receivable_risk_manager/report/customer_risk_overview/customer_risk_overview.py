import frappe


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"label": "Customer ID",
			"fieldname": "customer_id",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": "Customer Name",
			"fieldname": "customer_name",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": "Risk Level",
			"fieldname": "risk_level",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": "Risk Score",
			"fieldname": "risk_score",
			"fieldtype": "Int",
			"width": 100,
		},
		{
			"label": "Risk Confidence",
			"fieldname": "risk_confidence",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": "Open Amount",
			"fieldname": "open_amount",
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"label": "Total Invoice Amount",
			"fieldname": "total_invoice_amount",
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"label": "Total Invoices",
			"fieldname": "total_invoices",
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"label": "Closed Invoices",
			"fieldname": "closed_invoice_count",
			"fieldtype": "Int",
			"width": 120,
		},
		{
			"label": "Open Invoices",
			"fieldname": "open_invoice_count",
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"label": "Avg Payment Delay",
			"fieldname": "average_payment_delay",
			"fieldtype": "Float",
			"width": 130,
			"precision": 2,
		},
		{
			"label": "Late Payment Rate",
			"fieldname": "late_payment_rate",
			"fieldtype": "Percent",
			"width": 130,
		},
		{
			"label": "Risk Explanation",
			"fieldname": "risk_explanation",
			"fieldtype": "Data",
			"width": 500,
		},
	]


def get_data(filters):
	report_filters = build_report_filters(filters)

	return frappe.get_all(
		"Receivables Customer",
		filters=report_filters,
		fields=[
			"customer_id",
			"customer_name",
			"total_invoices",
			"closed_invoice_count",
			"open_invoice_count",
			"total_invoice_amount",
			"open_amount",
			"average_payment_delay",
			"late_payment_rate",
			"risk_score",
			"risk_level",
			"risk_confidence",
			"risk_explanation",
		],
		order_by="risk_score desc, open_amount desc",
	)


def build_report_filters(filters):
	report_filters = {}

	risk_level = filters.get("risk_level")
	if risk_level:
		report_filters["risk_level"] = risk_level

	min_open_amount = to_number(filters.get("min_open_amount"))
	if min_open_amount is not None:
		report_filters["open_amount"] = [">=", min_open_amount]

	min_late_payment_rate = to_number(filters.get("min_late_payment_rate"))
	if min_late_payment_rate is not None:
		report_filters["late_payment_rate"] = [">=", min_late_payment_rate]

	min_risk_score = to_number(filters.get("min_risk_score"))
	if min_risk_score is not None:
		report_filters["risk_score"] = [">=", min_risk_score]

	return report_filters


def to_number(value):
	if value in (None, ""):
		return None

	try:
		return float(value)
	except (TypeError, ValueError):
		return None

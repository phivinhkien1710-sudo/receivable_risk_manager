from receivable_risk_manager.services.dashboard_metrics import (
	get_aging_bucket_distribution,
	get_collection_actions_by_status,
	get_dashboard_summary,
	get_monthly_overdue_trend,
	get_outstanding_amount_by_risk_level,
	get_risk_level_distribution,
	get_top_risky_customers,
)


def execute(filters=None):
	filters = filters or {}

	columns = get_columns()
	data = get_top_risky_customers(limit=filters.get("top_customer_limit") or 10)
	chart = get_chart(filters)
	report_summary = get_report_summary()

	return columns, data, None, chart, report_summary


def get_columns():
	return [
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
			"label": "Risk Level",
			"fieldname": "risk_level",
			"fieldtype": "Data",
			"width": 100,
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
			"label": "Open Invoices",
			"fieldname": "open_invoice_count",
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"label": "Late Payment Rate",
			"fieldname": "late_payment_rate",
			"fieldtype": "Percent",
			"width": 130,
		},
		{
			"label": "Avg Payment Delay",
			"fieldname": "average_payment_delay",
			"fieldtype": "Float",
			"width": 130,
			"precision": 2,
		},
	]


def get_report_summary():
	summary = get_dashboard_summary()

	return [
		{
			"label": "Total Customers",
			"value": summary["total_customers"],
			"indicator": "Blue",
			"datatype": "Int",
		},
		{
			"label": "High Risk Customers",
			"value": summary["high_risk_customers"],
			"indicator": "Red",
			"datatype": "Int",
		},
		{
			"label": "Total Open Amount",
			"value": summary["total_open_amount"],
			"indicator": "Orange",
			"datatype": "Currency",
		},
		{
			"label": "High Risk Open Amount",
			"value": summary["high_risk_open_amount"],
			"indicator": "Red",
			"datatype": "Currency",
		},
		{
			"label": "Medium/High Open Invoices",
			"value": summary["medium_high_open_invoices"],
			"indicator": "Orange",
			"datatype": "Int",
		},
		{
			"label": "Open Collection Actions",
			"value": summary["open_collection_actions"],
			"indicator": "Blue",
			"datatype": "Int",
		},
		{
			"label": "High Priority Actions",
			"value": summary["high_priority_open_actions"],
			"indicator": "Red",
			"datatype": "Int",
		},
	]


def get_chart(filters):
	chart_metric = filters.get("chart_metric") or "Outstanding Amount by Risk Level"

	if chart_metric == "Customer Risk Distribution":
		return build_risk_distribution_chart()
	if chart_metric == "Aging Bucket Distribution":
		return build_aging_bucket_chart()
	if chart_metric == "Collection Actions by Status":
		return build_collection_actions_chart()
	if chart_metric == "Open Overdue Exposure by Due Month":
		return build_monthly_overdue_chart()

	return build_outstanding_amount_chart()


def build_outstanding_amount_chart():
	rows = get_outstanding_amount_by_risk_level()

	return {
		"data": {
			"labels": [row["risk_level"] for row in rows],
			"datasets": [
				{
					"name": "Open Amount",
					"values": [row["open_amount"] for row in rows],
				}
			],
		},
		"type": "bar",
		"height": 280,
		"colors": ["#f59e0b"],
	}


def build_risk_distribution_chart():
	rows = get_risk_level_distribution()

	return {
		"data": {
			"labels": [row["risk_level"] for row in rows],
			"datasets": [
				{
					"name": "Customers",
					"values": [row["customer_count"] for row in rows],
				}
			],
		},
		"type": "donut",
		"height": 280,
	}


def build_aging_bucket_chart():
	rows = get_aging_bucket_distribution()

	return {
		"data": {
			"labels": [row["aging_bucket"] for row in rows],
			"datasets": [
				{
					"name": "Open Invoice Amount",
					"values": [row["invoice_amount"] for row in rows],
				}
			],
		},
		"type": "bar",
		"height": 280,
		"colors": ["#ef4444"],
	}


def build_collection_actions_chart():
	rows = get_collection_actions_by_status()

	return {
		"data": {
			"labels": [row["status"] for row in rows],
			"datasets": [
				{
					"name": "Collection Actions",
					"values": [row["action_count"] for row in rows],
				}
			],
		},
		"type": "bar",
		"height": 280,
		"colors": ["#3b82f6"],
	}


def build_monthly_overdue_chart():
	rows = get_monthly_overdue_trend()

	return {
		"data": {
			"labels": [row["due_month"] for row in rows],
			"datasets": [
				{
					"name": "Open Overdue Amount",
					"values": [row["invoice_amount"] for row in rows],
				}
			],
		},
		"type": "line",
		"height": 280,
		"colors": ["#8b5cf6"],
	}

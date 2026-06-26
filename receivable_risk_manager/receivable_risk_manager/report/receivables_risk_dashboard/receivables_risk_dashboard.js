frappe.query_reports["Receivables Risk Dashboard"] = {
	filters: [
		{
			fieldname: "chart_metric",
			label: __("Chart Metric"),
			fieldtype: "Select",
			options:
				"Outstanding Amount by Risk Level\nCustomer Risk Distribution\nAging Bucket Distribution\nCollection Actions by Status\nOpen Overdue Exposure by Due Month",
			default: "Outstanding Amount by Risk Level",
		},
		{
			fieldname: "top_customer_limit",
			label: __("Top Customer Limit"),
			fieldtype: "Int",
			default: 10,
		},
	],
};

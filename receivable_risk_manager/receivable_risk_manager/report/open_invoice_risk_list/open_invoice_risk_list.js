frappe.query_reports["Open Invoice Risk List"] = {
	filters: [
		{
			fieldname: "risk_level",
			label: __("Risk Level"),
			fieldtype: "Select",
			options: "\nLow\nMedium\nHigh",
			description: __("Leave blank to show Medium and High risk invoices."),
		},
		{
			fieldname: "customer_id",
			label: __("Customer ID"),
			fieldtype: "Data",
		},
		{
			fieldname: "min_days_overdue",
			label: __("Minimum Days Overdue"),
			fieldtype: "Int",
		},
		{
			fieldname: "suggested_action",
			label: __("Suggested Action"),
			fieldtype: "Select",
			options: "\nEscalate Collection\nImmediate Follow-up\nSend Reminder\nMonitor",
		},
	],
};

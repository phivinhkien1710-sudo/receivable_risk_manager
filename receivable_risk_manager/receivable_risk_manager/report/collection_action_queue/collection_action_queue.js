frappe.query_reports["Collection Action Queue"] = {
	filters: [
		{
			fieldname: "priority",
			label: __("Priority"),
			fieldtype: "Select",
			options: "\nLow\nMedium\nHigh",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nOpen\nContacted\nPromised to Pay\nEscalated\nResolved",
			default: "Open",
			description: __("Leave as Open for the active collection queue."),
		},
		{
			fieldname: "action_type",
			label: __("Action Type"),
			fieldtype: "Select",
			options: "\nEscalate Collection\nImmediate Follow-up\nSend Reminder",
		},
		{
			fieldname: "customer_id",
			label: __("Customer ID"),
			fieldtype: "Data",
		},
	],
};

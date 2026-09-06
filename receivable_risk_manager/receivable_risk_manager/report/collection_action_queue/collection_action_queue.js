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
			options:
				"\nProposed\nOpen\nContacted\nPromised to Pay\nEscalated\nResolved\nRejected",
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
		{
			fieldname: "receivables_import_job",
			label: __("Import Batch"),
			fieldtype: "Link",
			options: "Receivables Import Job",
		},
		{
			fieldname: "ai_review_run",
			label: __("AI Review Run"),
			fieldtype: "Link",
			options: "AI Review Run",
		},
		{
			fieldname: "disagreements_only",
			label: __("Disagreements Only"),
			fieldtype: "Check",
			default: 0,
		},
	],
};

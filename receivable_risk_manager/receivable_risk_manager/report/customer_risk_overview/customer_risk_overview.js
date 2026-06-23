frappe.query_reports["Customer Risk Overview"] = {
	filters: [
		{
			fieldname: "risk_level",
			label: __("Risk Level"),
			fieldtype: "Select",
			options: "\nLow\nMedium\nHigh",
		},
		{
			fieldname: "min_open_amount",
			label: __("Minimum Open Amount"),
			fieldtype: "Currency",
		},
		{
			fieldname: "min_late_payment_rate",
			label: __("Minimum Late Payment Rate"),
			fieldtype: "Percent",
		},
		{
			fieldname: "min_risk_score",
			label: __("Minimum Risk Score"),
			fieldtype: "Int",
		},
	],
};

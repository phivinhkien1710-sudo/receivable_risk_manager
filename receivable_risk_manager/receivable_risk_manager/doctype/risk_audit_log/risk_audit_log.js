// Copyright (c) 2026, Kien Phi and contributors
// For license information, please see license.txt

frappe.ui.form.on("Risk Audit Log", {
	refresh(frm) {
		frm.disable_save();
	},
});

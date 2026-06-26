frappe.ui.form.on("Receivables Import Job", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(__("Validate"), () => {
			frappe.call({
				method:
					"receivable_risk_manager.receivable_risk_manager.doctype.receivables_import_job.receivables_import_job.validate_import_file",
				args: {
					job_name: frm.doc.name,
				},
				freeze: true,
				freeze_message: __("Validating CSV file..."),
				callback() {
					frm.reload_doc();
				},
			});
		});

		if (["Validated", "Completed With Errors"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Import"), () => {
				frappe.confirm(
					__(
						"This will import valid rows and run the receivables risk recalculation pipeline. Continue?"
					),
					() => {
						frappe.call({
							method:
								"receivable_risk_manager.receivable_risk_manager.doctype.receivables_import_job.receivables_import_job.run_import_job",
							args: {
								job_name: frm.doc.name,
							},
							freeze: true,
							freeze_message: __("Importing CSV and recalculating risk..."),
							callback() {
								frm.reload_doc();
							},
						});
					}
				);
			});
		}
	},
});

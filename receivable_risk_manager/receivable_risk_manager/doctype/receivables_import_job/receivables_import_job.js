const IMPORT_JOB_UPDATE_EVENT = "receivables_import_job_update";

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
						"This will queue the import and risk recalculation to run in the background. Continue?"
					),
					() => {
						frappe.call({
							method:
								"receivable_risk_manager.receivable_risk_manager.doctype.receivables_import_job.receivables_import_job.run_import_job",
							args: {
								job_name: frm.doc.name,
							},
							freeze: true,
							freeze_message: __("Queuing import job..."),
							callback() {
								frm.reload_doc();
								frappe.show_alert({
									message: __(
										"Import queued. This form will refresh automatically when it finishes."
									),
									indicator: "blue",
								});
							},
						});
					}
				);
			});
		}

		if (["Completed", "Completed With Errors"].includes(frm.doc.status)) {
			add_batch_workflow_menu(frm);
		}

		if (["Queued", "Importing"].includes(frm.doc.status)) {
			frm.dashboard.set_headline_alert(
				__(
					"This job is running in the background. The form will refresh automatically when it finishes."
				)
			);
			register_import_job_listener(frm);
		}
	},
});

function register_import_job_listener(frm) {
	if (frm.__import_job_listener_registered) {
		return;
	}
	frm.__import_job_listener_registered = true;

	frappe.realtime.on(IMPORT_JOB_UPDATE_EVENT, (data) => {
		if (data.job_name === frm.doc.name) {
			frm.__import_job_listener_registered = false;
			frm.reload_doc();
		}
	});
}


// The batch workflow menu. Every stage a user can run against this specific
// import lives here, so an import is something you *process* rather than an
// event that dumps rows into one global pool. Nothing here starts a stage on
// its own: each entry opens a pre-filled form or a scoped queue, and the user
// still clicks the start button there.
function add_batch_workflow_menu(frm) {
	frm.add_custom_button(
		__("Run AI Review"),
		() => {
			frappe.new_doc("AI Review Run", {
				receivables_import_job: frm.doc.name,
			});
		},
		__("Batch Workflow")
	);

	frm.add_custom_button(
		__("Review Proposals"),
		() => {
			frappe.set_route("query-report", "Collection Action Queue", {
				receivables_import_job: frm.doc.name,
				status: "Proposed",
			});
		},
		__("Batch Workflow")
	);

	frm.add_custom_button(
		__("Disagreements Only"),
		() => {
			frappe.set_route("query-report", "Collection Action Queue", {
				receivables_import_job: frm.doc.name,
				status: "Proposed",
				disagreements_only: 1,
			});
		},
		__("Batch Workflow")
	);

	frm.add_custom_button(
		__("AI Review History"),
		() => {
			frappe.set_route("List", "AI Review Run", {
				receivables_import_job: frm.doc.name,
			});
		},
		__("Batch Workflow")
	);
}

// Client script for AI Review Run.
//
// The Start button is the whole point of this doctype: it is the moment a human
// decides Claude should look at a batch. Before this existed, AI work happened
// invisibly inside a daily cron and there was no answer to "when does it run?".

frappe.ui.form.on("AI Review Run", {
	refresh(frm) {
		if (frm.is_new()) {
			frm.dashboard.set_headline_alert(
				__(
					"Save this run, then click Start Review. Leave Import Batch blank to review every open assessment."
				)
			);
			return;
		}

		if (["Draft", "Failed", "Completed With Errors"].includes(frm.doc.status)) {
			const label = frm.doc.status === "Draft" ? __("Start Review") : __("Resume Review");
			frm.add_custom_button(label, () => {
				frappe.confirm(
					__(
						"Claude will review the open invoices in scope and propose collection actions. Nothing is sent to any customer, and every proposal still needs your approval."
					),
					() => {
						frappe.call({
							method:
								"receivable_risk_manager.receivable_risk_manager.doctype.ai_review_run.ai_review_run.start_ai_review_run",
							args: { run_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Queueing review..."),
							callback: () => frm.reload_doc(),
						});
					}
				);
			}).addClass("btn-primary");
		}

		if (["Queued", "Running"].includes(frm.doc.status)) {
			frm.dashboard.set_headline_alert(
				__("This review is running in the background. Reload to see progress.")
			);
		}

		if (frm.doc.disagreed_with_rules > 0) {
			frm.add_custom_button(__("Review Disagreements"), () => {
				frappe.set_route("query-report", "Collection Action Queue", {
					ai_review_run: frm.doc.name,
					status: "Proposed",
					disagreements_only: 1,
				});
			});

			frm.dashboard.set_headline_alert(
				__("Claude disagreed with the rule engine on {0} of {1} invoices reviewed.", [
					frm.doc.disagreed_with_rules,
					frm.doc.assessments_reviewed,
				]),
				"orange"
			);
		}
	},
});

"""Wipes receivables data for a demo reset.

Deliberately raw SQL DELETE, not a per-document frappe.delete_doc() loop --
the doc-level path validates, checks permissions, and fires hooks per row,
which runs at the same order-of-magnitude cost as the import itself (~145
rows/sec measured on this bench). At 48,833 invoices that's minutes just to
delete; bulk SQL clears the same tables in seconds.

Leaves Receivables Import Job and AI Review Run history alone on purpose --
they're process/audit records of past runs, not invoice data, and there's no
reason a demo reset should erase the evidence that the app has real usage
history. Their receivables_import_job / ai_review_run references on the
deleted Collection Action rows just go dangling, which is harmless: Frappe
Link fields aren't enforced foreign keys, and nothing reads those old jobs
expecting the actions they once produced to still exist.
"""

import frappe


TABLES_IN_DELETE_ORDER = [
	"Collection Action",
	"Risk Audit Log",
	"Invoice Risk Assessment",
	"Receivables Batch Member",
	"Receivables Invoice",
	"Receivables Customer",
]


def wipe_all_receivables_data():
	"""Delete every row from the doctypes a re-import + recalculation would
	otherwise need to reconcile against. Irreversible outside of a backup.

	bench execute receivable_risk_manager.services.demo_reset.wipe_all_receivables_data
	"""

	counts = {}
	for doctype in TABLES_IN_DELETE_ORDER:
		table = f"tab{doctype}"
		before = frappe.db.count(doctype)
		frappe.db.sql(f"DELETE FROM `{table}`")
		counts[doctype] = before

	frappe.db.commit()
	return counts


def reset_and_import(csv_path, as_of_date="2020-05-31"):
	"""Wipe, then re-import through the real Receivables Import Job path (not
	the lower-level import_dataset() demo_setup.sh calls directly), so the
	result has real Receivables Batch Member rows and the completed job's
	Batch Workflow menu has something to attach to.

	csv_path must be absolute -- bench chdirs into sites/ before running any
	command, so a relative path resolves from the wrong place.

	bench execute receivable_risk_manager.services.demo_reset.reset_and_import --kwargs "{'csv_path': '/abs/path/to.csv'}"
	"""

	from receivable_risk_manager.services.import_jobs import run_import_job

	wipe_counts = wipe_all_receivables_data()

	with open(csv_path, "rb") as f:
		content = f.read()

	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": csv_path.rsplit("/", 1)[-1],
			"content": content,
			"is_private": 1,
		}
	).insert(ignore_permissions=True)

	job = frappe.new_doc("Receivables Import Job")
	job.csv_file = file_doc.file_url
	job.as_of_date = as_of_date
	job.insert(ignore_permissions=True)
	frappe.db.commit()

	result = run_import_job(job.name)

	return {"wiped": wipe_counts, "import_job": job.name, "result": result}

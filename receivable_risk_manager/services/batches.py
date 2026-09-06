"""Batch membership: which invoices arrived in which import.

Without this, an import is a one-off event that leaves no trace — every stage
after it operates on one undifferentiated pool of every invoice ever imported,
and "process today's batch" has no meaning. Membership is recorded in its own
join doctype rather than as a field on Receivables Invoice because later
imports update existing invoices, and a single field would be overwritten,
silently emptying the older batch.
"""

import frappe
from frappe.utils import now_datetime


BATCH_MEMBER_DOCTYPE = "Receivables Batch Member"
INVOICE_DOCTYPE = "Receivables Invoice"
ASSESSMENT_DOCTYPE = "Invoice Risk Assessment"
ACTION_DOCTYPE = "Collection Action"
COMMIT_EVERY = 500


def record_batch_membership(job_name, external_invoice_ids):
	"""Record which invoices belong to one import job. Idempotent."""

	summary = {"members_created": 0, "members_existing": 0, "invoices_not_found": 0}

	if not external_invoice_ids:
		return summary

	unique_ids = [i for i in dict.fromkeys(external_invoice_ids) if i]

	invoices = {
		row.invoice_id: row
		for row in frappe.get_all(
			INVOICE_DOCTYPE,
			filters={"invoice_id": ["in", unique_ids]},
			fields=["name", "invoice_id", "customer_id", "customer_name"],
		)
	}

	existing = {
		row.external_invoice_id
		for row in frappe.get_all(
			BATCH_MEMBER_DOCTYPE,
			filters={"receivables_import_job": job_name, "external_invoice_id": ["in", unique_ids]},
			fields=["external_invoice_id"],
		)
	}

	for invoice_id in unique_ids:
		if invoice_id in existing:
			summary["members_existing"] += 1
			continue

		invoice = invoices.get(invoice_id)
		if not invoice:
			summary["invoices_not_found"] += 1
			continue

		doc = frappe.new_doc(BATCH_MEMBER_DOCTYPE)
		doc.update(
			{
				"receivables_import_job": job_name,
				"receivables_invoice": invoice.name,
				"external_invoice_id": invoice_id,
				"customer_id": invoice.customer_id,
				"customer_name": invoice.customer_name,
				"added_on": now_datetime(),
			}
		)
		doc.insert(ignore_permissions=True)
		summary["members_created"] += 1

		if summary["members_created"] % COMMIT_EVERY == 0:
			frappe.db.commit()

	frappe.db.commit()
	return summary


def get_batch_invoice_ids(job_name):
	"""External invoice IDs belonging to one import batch."""

	return [
		row.external_invoice_id
		for row in frappe.get_all(
			BATCH_MEMBER_DOCTYPE,
			filters={"receivables_import_job": job_name},
			fields=["external_invoice_id"],
			limit_page_length=0,
		)
	]


def stamp_batch_on_downstream_records(job_name):
	"""Denormalise the batch onto assessments and actions for this batch's invoices.

	Membership itself lives in the join table, but the queue and reports need to
	filter by batch without a join on every read, so the batch is snapshotted
	onto each downstream record — the same approach Lead Outreach Manager uses
	when it stamps an import batch onto an Outreach Email.
	"""

	summary = {"assessments_stamped": 0, "actions_stamped": 0}
	invoice_ids = get_batch_invoice_ids(job_name)

	if not invoice_ids:
		return summary

	for doctype, key in ((ASSESSMENT_DOCTYPE, "assessments_stamped"), (ACTION_DOCTYPE, "actions_stamped")):
		rows = frappe.get_all(
			doctype,
			filters={
				"external_invoice_id": ["in", invoice_ids],
				"receivables_import_job": ["is", "not set"],
			},
			fields=["name"],
			limit_page_length=0,
		)

		for row in rows:
			frappe.db.set_value(doctype, row.name, "receivables_import_job", job_name, update_modified=False)
			summary[key] += 1

			if summary[key] % COMMIT_EVERY == 0:
				frappe.db.commit()

	frappe.db.commit()
	return summary

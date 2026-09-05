"""Guards the fix for a real usability complaint: Receivables Invoice,
Receivables Customer, and Invoice Risk Assessment are all named after opaque
source-data identifiers (a raw invoice_id/customer_id, or -- for the
assessment, which had no autoname at all -- a random hash), with no
customer context in the name itself. Collection Action's CA-##### name has
the same problem for a different reason. title_field is the safe fix:
Frappe shows it alongside `name` in list views and link dropdowns without
renaming the underlying record, which matters against real accumulated data
-- changing autoname instead would mean renaming every existing row and
rewriting every Link reference across all four doctypes."""

import frappe
from frappe.tests.utils import FrappeTestCase


TITLED_DOCTYPES = [
	"Receivables Invoice",
	"Receivables Customer",
	"Invoice Risk Assessment",
	"Collection Action",
]


class TestDoctypeTitles(FrappeTestCase):
	def test_customer_facing_doctypes_show_customer_name_as_title(self):
		for doctype in TITLED_DOCTYPES:
			meta = frappe.get_meta(doctype)
			self.assertEqual(
				meta.title_field,
				"customer_name",
				f"{doctype}.title_field regressed -- its `name` alone gives no "
				"indication of which customer the record belongs to.",
			)

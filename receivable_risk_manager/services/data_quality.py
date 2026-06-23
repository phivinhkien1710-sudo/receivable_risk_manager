import frappe


INVOICE_DOCTYPE = "Receivables Invoice"


def validate_receivables_data_quality():
	"""Return read-only data quality checks for Receivables Invoice records.

	This function does not modify data. It is intended for manual checks with
	bench execute and can also be reused by reports or health-check tools later.
	"""

	return {
		"total_invoices": count_invoices(),
		"missing_customer_id": count_missing_value("customer_id"),
		"missing_external_invoice_id": count_missing_value("invoice_id"),
		"missing_due_date": count_missing_value("due_date"),
		"missing_invoice_amount": count_missing_value("invoice_amount"),
		"open_invoices": count_invoices({"is_open": 1}),
		"closed_invoices": count_invoices({"is_open": 0}),
		"unique_customers": count_unique_customers(),
		"invalid_open_flags": count_invalid_open_flags(),
		"invoices_with_negative_amount": count_invoices(
			{"invoice_amount": ["<", 0]}
		),
		"invoices_with_clear_date_but_open": count_invoices(
			{
				"is_open": 1,
				"clear_date": ["is", "set"],
			}
		),
		"invoices_closed_without_clear_date": count_invoices(
			{
				"is_open": 0,
				"clear_date": ["is", "not set"],
			}
		),
	}


def count_invoices(filters=None):
	return frappe.db.count(INVOICE_DOCTYPE, filters=filters)


def count_missing_value(fieldname):
	return frappe.db.count(
		INVOICE_DOCTYPE,
		filters={
			fieldname: ["in", ["", None]],
		},
	)


def count_unique_customers():
	result = frappe.db.sql(
		f"""
		SELECT COUNT(DISTINCT customer_id)
		FROM `tab{INVOICE_DOCTYPE}`
		WHERE customer_id IS NOT NULL
		  AND customer_id != ''
		"""
	)

	return int(result[0][0] or 0)


def count_invalid_open_flags():
	result = frappe.db.sql(
		f"""
		SELECT COUNT(*)
		FROM `tab{INVOICE_DOCTYPE}`
		WHERE is_open IS NULL
		   OR is_open NOT IN (0, 1)
		"""
	)

	return int(result[0][0] or 0)

import frappe
from frappe.utils import now_datetime


INVOICE_DOCTYPE = "Receivables Invoice"
CUSTOMER_DOCTYPE = "Receivables Customer"
BATCH_SIZE = 200


def recalculate_receivables_customers(limit: int | None = None) -> dict:
	"""Aggregate Receivables Invoice rows into Receivables Customer records.

	This function is safe to rerun. It creates one Receivables Customer per
	customer_id when missing, otherwise updates the existing record.
	"""

	summary = {
		"customers_seen": 0,
		"customers_created": 0,
		"customers_updated": 0,
		"customers_failed": 0,
		"customers_skipped": 0,
	}

	customer_rows = _get_customer_ids(limit=limit)

	for row in customer_rows:
		customer_id = row.get("customer_id")
		if not customer_id:
			summary["customers_skipped"] += 1
			continue

		summary["customers_seen"] += 1

		try:
			metrics = _calculate_customer_metrics(customer_id)
			created = _create_or_update_customer(metrics)

			if created:
				summary["customers_created"] += 1
			else:
				summary["customers_updated"] += 1

			if summary["customers_seen"] % BATCH_SIZE == 0:
				frappe.db.commit()

		except Exception:
			summary["customers_failed"] += 1
			frappe.log_error(
				title=f"Receivables Customer aggregation failed: {customer_id}",
				message=frappe.get_traceback(),
			)

	frappe.db.commit()
	return summary


def _get_customer_ids(limit: int | None = None) -> list[dict]:
	query = f"""
		SELECT DISTINCT customer_id
		FROM `tab{INVOICE_DOCTYPE}`
		WHERE customer_id IS NOT NULL
		  AND customer_id != ''
		ORDER BY customer_id
	"""

	if limit is not None:
		query += " LIMIT %(limit)s"
		return frappe.db.sql(query, {"limit": int(limit)}, as_dict=True)

	return frappe.db.sql(query, as_dict=True)


def _calculate_customer_metrics(customer_id: str) -> dict:
	late_payment_expression = _get_late_payment_expression()

	metrics = frappe.db.sql(
		f"""
		SELECT
			customer_id,
			COUNT(*) AS total_invoices,
			SUM(CASE WHEN IFNULL(is_open, 0) = 0 THEN 1 ELSE 0 END) AS closed_invoice_count,
			SUM(CASE WHEN IFNULL(is_open, 0) = 1 THEN 1 ELSE 0 END) AS open_invoice_count,
			SUM(IFNULL(invoice_amount, 0)) AS total_invoice_amount,
			SUM(CASE WHEN IFNULL(is_open, 0) = 1 THEN IFNULL(invoice_amount, 0) ELSE 0 END) AS open_amount,
			AVG(
				CASE
					WHEN IFNULL(is_open, 0) = 0 AND payment_delay_days IS NOT NULL
					THEN payment_delay_days
					ELSE NULL
				END
			) AS average_payment_delay,
			SUM(
				CASE
					WHEN IFNULL(is_open, 0) = 0 AND {late_payment_expression}
					THEN 1
					ELSE 0
				END
			) AS late_invoice_count,
			MIN(posting_date) AS first_invoice_date,
			MAX(posting_date) AS last_invoice_date
		FROM `tab{INVOICE_DOCTYPE}`
		WHERE customer_id = %(customer_id)s
		GROUP BY customer_id
		""",
		{"customer_id": customer_id},
		as_dict=True,
	)[0]

	name_and_currency = _get_most_common_name_and_currency(customer_id)

	closed_invoice_count = metrics.closed_invoice_count or 0
	late_invoice_count = metrics.late_invoice_count or 0
	late_payment_rate = (
		(late_invoice_count / closed_invoice_count) * 100 if closed_invoice_count else 0
	)

	return {
		"customer_id": customer_id,
		"customer_name": name_and_currency.get("customer_name"),
		"default_currency": name_and_currency.get("currency"),
		"business_code": name_and_currency.get("business_code"),
		"total_invoices": metrics.total_invoices or 0,
		"closed_invoice_count": closed_invoice_count,
		"open_invoice_count": metrics.open_invoice_count or 0,
		"total_invoice_amount": metrics.total_invoice_amount or 0,
		"open_amount": metrics.open_amount or 0,
		"average_payment_delay": metrics.average_payment_delay or 0,
		"late_payment_rate": late_payment_rate,
		"first_invoice_date": metrics.first_invoice_date,
		"last_invoice_date": metrics.last_invoice_date,
	}


def _get_most_common_name_and_currency(customer_id: str) -> dict:
	rows = frappe.db.sql(
		f"""
		SELECT
			customer_name,
			currency,
			business_code,
			COUNT(*) AS row_count
		FROM `tab{INVOICE_DOCTYPE}`
		WHERE customer_id = %(customer_id)s
		GROUP BY customer_name, currency, business_code
		ORDER BY row_count DESC, customer_name ASC
		LIMIT 1
		""",
		{"customer_id": customer_id},
		as_dict=True,
	)

	return rows[0] if rows else {}


def _create_or_update_customer(metrics: dict) -> bool:
	customer_id = metrics["customer_id"]
	existing_name = frappe.db.exists(CUSTOMER_DOCTYPE, {"customer_id": customer_id})

	if existing_name:
		doc = frappe.get_doc(CUSTOMER_DOCTYPE, existing_name)
		created = False
	else:
		doc = frappe.new_doc(CUSTOMER_DOCTYPE)
		doc.customer_id = customer_id
		created = True

	doc.update(
		{
			"customer_name": metrics["customer_name"],
			"business_code": metrics["business_code"],
			"default_currency": metrics["default_currency"],
			"total_invoices": metrics["total_invoices"],
			"closed_invoice_count": metrics["closed_invoice_count"],
			"open_invoice_count": metrics["open_invoice_count"],
			"total_invoice_amount": metrics["total_invoice_amount"],
			"open_amount": metrics["open_amount"],
			"average_payment_delay": metrics["average_payment_delay"],
			"late_payment_rate": metrics["late_payment_rate"],
			"last_calculated_on": now_datetime(),
			# Backward-compatible summary fields from the earlier DocType version.
			"invoice_count": metrics["total_invoices"],
			"first_invoice_date": metrics["first_invoice_date"],
			"last_invoice_date": metrics["last_invoice_date"],
		}
	)
	doc.save(ignore_permissions=True)

	return created


def _get_late_payment_expression() -> str:
	"""Return SQL condition for late closed invoices.

	The requested source field is is_late, but the current MVP DocType stores
	this as late_payment_status. Supporting both keeps the service tolerant of
	either schema.
	"""

	meta = frappe.get_meta(INVOICE_DOCTYPE)
	if meta.has_field("is_late"):
		return "IFNULL(is_late, 0) = 1"

	return "late_payment_status = 'Late'"

import csv
from datetime import date
from pathlib import Path

import frappe
from frappe.utils import getdate, now_datetime


DEFAULT_AS_OF_DATE = "2020-05-31"
DEFAULT_BATCH_SIZE = 500


def import_dataset(csv_path: str, limit: int | None = None, as_of_date: str = DEFAULT_AS_OF_DATE) -> dict:
	"""Import cleaned receivables CSV rows into custom DocTypes.

	This function is intentionally idempotent:
	- Receivables Customer is keyed by customer_id.
	- Receivables Invoice is keyed by invoice_id.
	- Re-running the importer updates existing records instead of creating duplicates.
	"""

	path = Path(csv_path).expanduser()
	if not path.exists():
		frappe.throw(f"CSV file not found: {path}")

	stats = {
		"rows_seen": 0,
		"customers_created": 0,
		"customers_updated": 0,
		"invoices_created": 0,
		"invoices_updated": 0,
		"customers_summarized": 0,
	}
	touched_customers: set[str] = set()

	with path.open(newline="", encoding="utf-8") as csv_file:
		reader = csv.DictReader(csv_file)

		for raw_row in reader:
			if limit is not None and stats["rows_seen"] >= int(limit):
				break

			row = normalize_csv_row(raw_row, as_of_date=as_of_date)
			stats["rows_seen"] += 1

			customer_name, customer_created = get_or_create_receivables_customer(row)
			if customer_created:
				stats["customers_created"] += 1
			else:
				stats["customers_updated"] += 1

			invoice_created = create_or_update_receivables_invoice(row, customer_name)
			if invoice_created:
				stats["invoices_created"] += 1
			else:
				stats["invoices_updated"] += 1

			touched_customers.add(row["customer_id"])

			if stats["rows_seen"] % DEFAULT_BATCH_SIZE == 0:
				frappe.db.commit()

	for customer_id in sorted(touched_customers):
		update_customer_summary(customer_id)
		stats["customers_summarized"] += 1

	frappe.db.commit()
	return stats


def normalize_csv_row(row: dict, as_of_date: str = DEFAULT_AS_OF_DATE) -> dict:
	"""Convert CSV strings into values that match the custom DocTypes."""

	is_open = to_int(row.get("is_open")) == 1
	payment_delay_days = to_optional_int(row.get("payment_delay_days"))
	is_late = to_optional_int(row.get("is_late"))
	due_date = clean_date(row.get("due_date"))
	days_overdue = calculate_days_overdue(due_date, is_open, as_of_date)

	return {
		"business_code": clean_text(row.get("business_code")),
		"customer_id": clean_text(row.get("customer_id")),
		"customer_name": clean_text(row.get("customer_name")),
		"clear_date": clean_date(row.get("clear_date")),
		"business_year": to_optional_int(row.get("business_year")),
		"doc_id": clean_text(row.get("doc_id")),
		"posting_date": clean_date(row.get("posting_date")),
		"document_create_date": clean_date(row.get("document_create_date")),
		"document_create_date_1": clean_date(row.get("document_create_date_1")),
		"due_date": due_date,
		"currency": clean_text(row.get("currency")),
		"document_type": clean_text(row.get("document_type")),
		"posting_id": to_optional_int(row.get("posting_id")),
		"invoice_amount": to_float(row.get("invoice_amount")),
		"baseline_create_date": clean_date(row.get("baseline_create_date")),
		"payment_terms": clean_text(row.get("payment_terms")),
		"invoice_id": clean_text(row.get("invoice_id")),
		"is_open": 1 if is_open else 0,
		"payment_delay_days": payment_delay_days,
		"late_payment_status": get_late_payment_status(is_open, is_late),
		"days_overdue": days_overdue,
		"status": get_invoice_status(is_open, days_overdue),
	}


def get_or_create_receivables_customer(row: dict) -> tuple[str, bool]:
	"""Create or update one Receivables Customer.

	Returns:
	    tuple: (customer document name, created?)
	"""

	customer_id = row["customer_id"]
	if not customer_id:
		frappe.throw("Cannot import row without customer_id")

	existing_name = frappe.db.exists("Receivables Customer", customer_id)
	if existing_name:
		doc = frappe.get_doc("Receivables Customer", existing_name)
		created = False
	else:
		doc = frappe.new_doc("Receivables Customer")
		doc.customer_id = customer_id
		created = True

	doc.customer_name = row["customer_name"]
	doc.business_code = row["business_code"]
	doc.default_currency = row["currency"]
	doc.save(ignore_permissions=True)

	return doc.name, created


def create_or_update_receivables_invoice(row: dict, customer_name: str) -> bool:
	"""Create or update one Receivables Invoice.

	Returns:
	    bool: True if created, False if updated.
	"""

	invoice_id = row["invoice_id"]
	if not invoice_id:
		frappe.throw("Cannot import row without invoice_id")

	existing_name = frappe.db.exists("Receivables Invoice", invoice_id)
	if existing_name:
		doc = frappe.get_doc("Receivables Invoice", existing_name)
		created = False
	else:
		doc = frappe.new_doc("Receivables Invoice")
		doc.invoice_id = invoice_id
		created = True

	doc.update(
		{
			"doc_id": row["doc_id"],
			"receivables_customer": customer_name,
			"customer_id": row["customer_id"],
			"customer_name": row["customer_name"],
			"business_code": row["business_code"],
			"business_year": row["business_year"],
			"posting_date": row["posting_date"],
			"due_date": row["due_date"],
			"clear_date": row["clear_date"],
			"document_create_date": row["document_create_date"],
			"document_create_date_1": row["document_create_date_1"],
			"baseline_create_date": row["baseline_create_date"],
			"currency": row["currency"],
			"document_type": row["document_type"],
			"posting_id": row["posting_id"],
			"payment_terms": row["payment_terms"],
			"invoice_amount": row["invoice_amount"],
			"is_open": row["is_open"],
			"late_payment_status": row["late_payment_status"],
			"payment_delay_days": row["payment_delay_days"],
			"days_overdue": row["days_overdue"],
			"status": row["status"],
			"imported_on": now_datetime(),
		}
	)
	doc.save(ignore_permissions=True)
	return created


def update_customer_summary(customer_id: str) -> None:
	"""Refresh summary fields on Receivables Customer after invoices are imported."""

	customer_name = frappe.db.exists("Receivables Customer", customer_id)
	if not customer_name:
		return

	summary = frappe.db.sql(
		"""
		SELECT
			COUNT(*) AS invoice_count,
			MIN(posting_date) AS first_invoice_date,
			MAX(posting_date) AS last_invoice_date
		FROM `tabReceivables Invoice`
		WHERE customer_id = %s
		""",
		customer_id,
		as_dict=True,
	)[0]

	frappe.db.set_value(
		"Receivables Customer",
		customer_name,
		{
			"invoice_count": summary.invoice_count or 0,
			"first_invoice_date": summary.first_invoice_date,
			"last_invoice_date": summary.last_invoice_date,
		},
		update_modified=False,
	)


def get_invoice_status(is_open: bool, days_overdue: int) -> str:
	if not is_open:
		return "Closed"
	if days_overdue > 0:
		return "Overdue"
	return "Open"


def get_late_payment_status(is_open: bool, is_late: int | None) -> str:
	if is_open:
		return "Unknown"
	if is_late == 1:
		return "Late"
	return "On Time"


def calculate_days_overdue(due_date: str | None, is_open: bool, as_of_date: str) -> int:
	if not is_open or not due_date:
		return 0

	delta = getdate(as_of_date) - getdate(due_date)
	return max(delta.days, 0)


def clean_text(value) -> str | None:
	if value is None:
		return None
	value = str(value).strip()
	return value or None


def clean_date(value) -> str | None:
	value = clean_text(value)
	if not value:
		return None
	return str(getdate(value))


def to_float(value) -> float:
	value = clean_text(value)
	if not value:
		return 0.0
	return float(value)


def to_int(value) -> int:
	value = clean_text(value)
	if not value:
		return 0
	return int(float(value))


def to_optional_int(value) -> int | None:
	value = clean_text(value)
	if not value:
		return None
	return int(float(value))

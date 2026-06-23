import csv
from pathlib import Path

import frappe


CUSTOMER_EXPORT_FIELDS = [
	"customer_id",
	"customer_name",
	"business_code",
	"default_currency",
	"total_invoices",
	"closed_invoice_count",
	"open_invoice_count",
	"total_invoice_amount",
	"open_amount",
	"average_payment_delay",
	"late_payment_rate",
	"risk_score",
	"risk_level",
	"risk_explanation",
	"last_calculated_on",
	"risk_last_calculated_on",
]


def export_first_receivables_customers(
	limit: int = 50,
	output_path: str = "/Users/phikien/erpnext/frappe-bench/apps/receivable_risk_manager/ml/data/receivables_customers_first_50.csv",
):
	rows = frappe.get_all(
		"Receivables Customer",
		fields=CUSTOMER_EXPORT_FIELDS,
		order_by="customer_id asc",
		limit_page_length=int(limit),
	)

	path = Path(output_path)
	path.parent.mkdir(parents=True, exist_ok=True)

	with path.open("w", newline="", encoding="utf-8") as csv_file:
		writer = csv.DictWriter(csv_file, fieldnames=CUSTOMER_EXPORT_FIELDS)
		writer.writeheader()
		writer.writerows(rows)

	return {
		"output_path": str(path),
		"rows_exported": len(rows),
	}

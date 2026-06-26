import tempfile
import unittest
from pathlib import Path

from receivable_risk_manager.services.import_jobs import (
	REQUIRED_COLUMNS,
	summarize_import_errors,
	validate_csv_file,
	validate_csv_headers,
	validate_csv_row,
)


class TestImportJobValidation(unittest.TestCase):
	def test_validate_csv_headers_accepts_required_columns(self):
		self.assertEqual(validate_csv_headers(REQUIRED_COLUMNS), [])

	def test_validate_csv_headers_reports_missing_required_columns(self):
		errors = validate_csv_headers(["customer_id", "invoice_id"])

		self.assertEqual(len(errors), 1)
		self.assertIn("posting_date", errors[0])
		self.assertIn("invoice_amount", errors[0])

	def test_validate_csv_row_accepts_valid_row(self):
		row = {
			"customer_id": "CUST-001",
			"invoice_id": "INV-001",
			"posting_date": "2020-01-01",
			"due_date": "2020-02-01",
			"invoice_amount": "100.50",
			"is_open": "1",
		}

		self.assertEqual(validate_csv_row(row, 2), [])

	def test_validate_csv_row_reports_invalid_values(self):
		row = {
			"customer_id": "",
			"invoice_id": "INV-001",
			"posting_date": "not-a-date",
			"due_date": "2020-02-01",
			"invoice_amount": "abc",
			"is_open": "3",
		}

		errors = validate_csv_row(row, 2)

		self.assertIn("Row 2: Missing customer_id", errors)
		self.assertIn("Row 2: Invalid posting_date", errors)
		self.assertIn("Row 2: Invalid invoice_amount", errors)
		self.assertIn("Row 2: is_open must be 0 or 1", errors)

	def test_summarize_import_errors_limits_output(self):
		errors = [f"Row {index}: Error" for index in range(1, 25)]
		summary = summarize_import_errors(errors, limit=3)

		self.assertIn("Row 1: Error", summary)
		self.assertIn("... 21 more errors", summary)
		self.assertNotIn("Row 4: Error", summary)

	def test_validate_csv_file_counts_valid_and_invalid_rows(self):
		csv_content = (
			"customer_id,invoice_id,posting_date,due_date,invoice_amount,is_open\n"
			"CUST-001,INV-001,2020-01-01,2020-02-01,100,1\n"
			",INV-002,2020-01-01,2020-02-01,100,1\n"
		)

		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as csv_file:
			csv_file.write(csv_content)
			csv_path = csv_file.name

		try:
			result = validate_csv_file(csv_path)
		finally:
			Path(csv_path).unlink(missing_ok=True)

		self.assertEqual(result["total_rows"], 2)
		self.assertEqual(result["valid_rows"], 1)
		self.assertEqual(result["invalid_rows"], 1)
		self.assertEqual(len(result["valid_data_rows"]), 1)


if __name__ == "__main__":
	unittest.main()

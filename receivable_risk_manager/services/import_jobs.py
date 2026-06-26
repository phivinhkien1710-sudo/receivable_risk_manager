import csv
import tempfile
from datetime import datetime
from pathlib import Path


EXPECTED_COLUMNS = [
	"business_code",
	"customer_id",
	"customer_name",
	"clear_date",
	"business_year",
	"doc_id",
	"posting_date",
	"document_create_date",
	"document_create_date_1",
	"due_date",
	"currency",
	"document_type",
	"posting_id",
	"invoice_amount",
	"baseline_create_date",
	"payment_terms",
	"invoice_id",
	"is_open",
	"payment_delay_days",
	"is_late",
]

REQUIRED_COLUMNS = [
	"customer_id",
	"invoice_id",
	"posting_date",
	"due_date",
	"invoice_amount",
	"is_open",
]

MAX_ERROR_MESSAGES = 20


def validate_import_file(job_name):
	"""Validate an attached CSV file without importing rows."""

	frappe = get_frappe()
	job = frappe.get_doc("Receivables Import Job", job_name)
	file_path = get_attached_file_path(job)

	result = validate_csv_file(file_path)
	update_job_with_validation_result(job, result)

	return result


def run_import_job(job_name):
	"""Import valid CSV rows from a Receivables Import Job and recalculate risk."""

	frappe = get_frappe()
	job = frappe.get_doc("Receivables Import Job", job_name)
	file_path = get_attached_file_path(job)
	validation = validate_csv_file(file_path)
	update_job_with_validation_result(job, validation)

	if validation["valid_rows"] == 0:
		job.status = "Validation Failed"
		job.completed_on = frappe.utils.now_datetime()
		job.save(ignore_permissions=True)
		frappe.throw("No valid rows found. Fix the CSV file before importing.")

	job.status = "Importing"
	job.started_on = frappe.utils.now_datetime()
	job.imported_by = frappe.session.user
	job.save(ignore_permissions=True)
	frappe.db.commit()

	try:
		with write_valid_rows_to_temp_csv(validation["valid_data_rows"]) as temp_csv_path:
			from receivable_risk_manager.imports.invoice_imports import import_dataset

			import_result = import_dataset(
				temp_csv_path,
				as_of_date=str(job.as_of_date or "2020-05-31"),
			)

		recalculation_result = run_recalculation()
		update_job_with_import_result(job, import_result, recalculation_result, validation)
		return {
			"validation": summarize_validation_result(validation),
			"import": import_result,
			"recalculation": recalculation_result,
			"status": job.status,
		}

	except Exception:
		job.status = "Failed"
		job.completed_on = frappe.utils.now_datetime()
		job.error_summary = "Import failed. Check Error Log for technical details."
		job.save(ignore_permissions=True)
		frappe.log_error(
			title=f"Receivables Import Job failed: {job.name}",
			message=frappe.get_traceback(),
		)
		frappe.db.commit()
		raise


def validate_csv_file(file_path):
	"""Return validation details for a CSV file path."""

	total_rows = 0
	valid_rows = 0
	invalid_rows = 0
	errors = []
	valid_data_rows = []

	with Path(file_path).open(newline="", encoding="utf-8-sig") as csv_file:
		reader = csv.DictReader(csv_file)
		header_errors = validate_csv_headers(reader.fieldnames or [])

		if header_errors:
			return {
				"total_rows": 0,
				"valid_rows": 0,
				"invalid_rows": 0,
				"errors": header_errors,
				"valid_data_rows": [],
			}

		for row_number, row in enumerate(reader, start=2):
			total_rows += 1
			row_errors = validate_csv_row(row, row_number)

			if row_errors:
				invalid_rows += 1
				errors.extend(row_errors)
				continue

			valid_rows += 1
			valid_data_rows.append(row)

	return {
		"total_rows": total_rows,
		"valid_rows": valid_rows,
		"invalid_rows": invalid_rows,
		"errors": errors,
		"valid_data_rows": valid_data_rows,
	}


def validate_csv_headers(headers):
	headers = {clean_text(header) for header in headers if clean_text(header)}
	missing_columns = [column for column in REQUIRED_COLUMNS if column not in headers]

	if not missing_columns:
		return []

	return [
		"Missing required columns: " + ", ".join(missing_columns),
	]


def validate_csv_row(row, row_number):
	errors = []

	for column in REQUIRED_COLUMNS:
		if not clean_text(row.get(column)):
			errors.append(f"Row {row_number}: Missing {column}")

	if clean_text(row.get("invoice_amount")):
		try:
			float(clean_text(row.get("invoice_amount")))
		except ValueError:
			errors.append(f"Row {row_number}: Invalid invoice_amount")

	if clean_text(row.get("is_open")):
		try:
			open_flag = int(float(clean_text(row.get("is_open"))))
			if open_flag not in (0, 1):
				errors.append(f"Row {row_number}: is_open must be 0 or 1")
		except ValueError:
			errors.append(f"Row {row_number}: Invalid is_open")

	for date_column in (
		"posting_date",
		"due_date",
		"clear_date",
		"document_create_date",
		"document_create_date_1",
		"baseline_create_date",
	):
		if clean_text(row.get(date_column)) and not is_valid_date(row.get(date_column)):
			errors.append(f"Row {row_number}: Invalid {date_column}")

	return errors


def summarize_import_errors(errors, limit=MAX_ERROR_MESSAGES):
	if not errors:
		return ""

	visible_errors = errors[:limit]
	summary = "\n".join(visible_errors)
	remaining_count = len(errors) - len(visible_errors)

	if remaining_count > 0:
		summary += f"\n... {remaining_count} more errors"

	return summary


def summarize_validation_result(result):
	return {
		"total_rows": result["total_rows"],
		"valid_rows": result["valid_rows"],
		"invalid_rows": result["invalid_rows"],
		"errors": summarize_import_errors(result["errors"]),
	}


def update_job_with_validation_result(job, result):
	job.total_rows = result["total_rows"]
	job.valid_rows = result["valid_rows"]
	job.invalid_rows = result["invalid_rows"]
	job.validation_summary = (
		f"Total rows: {result['total_rows']}\n"
		f"Valid rows: {result['valid_rows']}\n"
		f"Invalid rows: {result['invalid_rows']}"
	)
	job.error_summary = summarize_import_errors(result["errors"])

	if result["errors"]:
		job.status = "Validation Failed" if result["valid_rows"] == 0 else "Validated"
	else:
		job.status = "Validated"

	job.save(ignore_permissions=True)
	get_frappe().db.commit()


def update_job_with_import_result(job, import_result, recalculation_result, validation):
	frappe = get_frappe()
	job.imported_rows = validation["valid_rows"]
	job.customers_created = import_result.get("customers_created", 0)
	job.customers_updated = import_result.get("customers_updated", 0)
	job.invoices_created = import_result.get("invoices_created", 0)
	job.invoices_updated = import_result.get("invoices_updated", 0)
	job.customers_summarized = import_result.get("customers_summarized", 0)
	job.completed_on = frappe.utils.now_datetime()

	if recalculation_result.get("status") == "success":
		job.recalculation_status = "Completed"
	elif recalculation_result.get("status") == "completed_with_errors":
		job.recalculation_status = "Completed With Errors"
	else:
		job.recalculation_status = "Failed"

	if validation["invalid_rows"] > 0 or recalculation_result.get("status") == "completed_with_errors":
		job.status = "Completed With Errors"
	else:
		job.status = "Completed"

	job.save(ignore_permissions=True)
	frappe.db.commit()


def get_attached_file_path(job):
	frappe = get_frappe()

	if not job.csv_file:
		frappe.throw("Please attach a CSV file before validating.")

	file_url = job.csv_file
	if file_url.startswith("/private/files/"):
		return frappe.get_site_path("private", "files", file_url.split("/private/files/", 1)[1])
	if file_url.startswith("/files/"):
		return frappe.get_site_path("public", "files", file_url.split("/files/", 1)[1])

	file_doc_name = frappe.db.exists("File", {"file_url": file_url})
	if file_doc_name:
		file_doc = frappe.get_doc("File", file_doc_name)
		return file_doc.get_full_path()

	frappe.throw(f"Could not resolve attached file path: {file_url}")


def write_valid_rows_to_temp_csv(valid_rows):
	temp_file = tempfile.NamedTemporaryFile(
		mode="w",
		newline="",
		encoding="utf-8",
		suffix=".csv",
		delete=False,
	)

	fieldnames = get_fieldnames_for_temp_csv(valid_rows)
	writer = csv.DictWriter(temp_file, fieldnames=fieldnames, extrasaction="ignore")
	writer.writeheader()
	writer.writerows(valid_rows)
	temp_file.close()

	return TemporaryCsvPath(temp_file.name)


def get_fieldnames_for_temp_csv(valid_rows):
	if not valid_rows:
		return EXPECTED_COLUMNS

	fieldnames = list(valid_rows[0].keys())
	for column in EXPECTED_COLUMNS:
		if column not in fieldnames:
			fieldnames.append(column)

	return fieldnames


def run_recalculation():
	from receivable_risk_manager.tasks import run_full_recalculation

	return run_full_recalculation()


def clean_text(value):
	if value is None:
		return None

	value = str(value).strip()
	return value or None


def is_valid_date(value):
	value = clean_text(value)
	if not value:
		return True

	for date_format in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
		try:
			datetime.strptime(value, date_format)
			return True
		except ValueError:
			continue

	return False


class TemporaryCsvPath:
	def __init__(self, path):
		self.path = path

	def __enter__(self):
		return self.path

	def __exit__(self, exc_type, exc_value, traceback):
		try:
			Path(self.path).unlink(missing_ok=True)
		except OSError:
			pass


def get_frappe():
	import frappe

	return frappe

# Copyright (c) 2026, kien and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ReceivablesImportJob(Document):
	def validate(self):
		if self.csv_file and not self.csv_file.lower().endswith(".csv"):
			frappe.throw("Please attach a CSV file.")


@frappe.whitelist()
def validate_import_file(job_name):
	from receivable_risk_manager.services.import_jobs import (
		validate_import_file as validate_job_file,
	)

	return validate_job_file(job_name)


@frappe.whitelist()
def run_import_job(job_name):
	from receivable_risk_manager.services.import_jobs import run_import_job as run_job

	return run_job(job_name)

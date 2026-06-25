# Copyright (c) 2026, kien and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ReceivablesInvoice(Document):
	def validate(self):
		self._validate_amounts()
		self._validate_status()

	def _validate_amounts(self):
		if (self.invoice_amount or 0) < 0:
			frappe.throw("Invoice Amount cannot be negative.")

		if (self.days_overdue or 0) < 0:
			frappe.throw("Days Overdue cannot be negative.")

	def _validate_status(self):
		valid_statuses = {"Open", "Closed", "Overdue"}
		if self.status and self.status not in valid_statuses:
			frappe.throw("Status must be Open, Closed, or Overdue.")

		valid_late_payment_statuses = {"Unknown", "Late", "On Time"}
		if self.late_payment_status and self.late_payment_status not in valid_late_payment_statuses:
			frappe.throw("Late Payment Status must be Unknown, Late, or On Time.")

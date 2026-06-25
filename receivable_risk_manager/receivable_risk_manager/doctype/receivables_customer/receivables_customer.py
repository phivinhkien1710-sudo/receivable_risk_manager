# Copyright (c) 2026, kien and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ReceivablesCustomer(Document):
	def validate(self):
		self._validate_counts()
		self._validate_risk_fields()

	def _validate_counts(self):
		count_fields = (
			"total_invoices",
			"closed_invoice_count",
			"open_invoice_count",
			"invoice_count",
		)

		for fieldname in count_fields:
			if (self.get(fieldname) or 0) < 0:
				frappe.throw(f"{frappe.unscrub(fieldname)} cannot be negative.")

		total_invoices = self.total_invoices or 0
		closed_invoice_count = self.closed_invoice_count or 0
		open_invoice_count = self.open_invoice_count or 0

		if total_invoices and closed_invoice_count + open_invoice_count > total_invoices:
			frappe.throw("Closed Invoice Count plus Open Invoice Count cannot exceed Total Invoices.")

	def _validate_risk_fields(self):
		if self.risk_score is not None and not 0 <= self.risk_score <= 100:
			frappe.throw("Risk Score must be between 0 and 100.")

		valid_levels = {"Low", "Medium", "High"}
		if self.risk_level and self.risk_level not in valid_levels:
			frappe.throw("Risk Level must be Low, Medium, or High.")

		if self.get("risk_confidence") and self.risk_confidence not in valid_levels:
			frappe.throw("Risk Confidence must be Low, Medium, or High.")

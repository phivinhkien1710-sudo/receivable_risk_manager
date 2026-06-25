# Copyright (c) 2026, kien and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class InvoiceRiskAssessment(Document):
	def validate(self):
		self._validate_risk_fields()
		self._validate_invoice_fields()

	def _validate_risk_fields(self):
		if self.risk_score is not None and not 0 <= self.risk_score <= 100:
			frappe.throw("Risk Score must be between 0 and 100.")

		if self.customer_risk_score is not None and not 0 <= self.customer_risk_score <= 100:
			frappe.throw("Customer Risk Score must be between 0 and 100.")

		valid_levels = {"Low", "Medium", "High"}
		if self.risk_level and self.risk_level not in valid_levels:
			frappe.throw("Risk Level must be Low, Medium, or High.")

		if self.customer_risk_level and self.customer_risk_level not in valid_levels:
			frappe.throw("Customer Risk Level must be Low, Medium, or High.")

	def _validate_invoice_fields(self):
		if (self.days_overdue or 0) < 0:
			frappe.throw("Days Overdue cannot be negative.")

		if (self.invoice_amount or 0) < 0:
			frappe.throw("Invoice Amount cannot be negative.")

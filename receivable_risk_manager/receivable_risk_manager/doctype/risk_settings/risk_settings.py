# Copyright (c) 2026, kien and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class RiskSettings(Document):
	def validate(self):
		self._set_missing_defaults()
		self._validate_thresholds()
		self._validate_weights()

	def _set_missing_defaults(self):
		defaults = {
			"high_risk_threshold": 70,
			"medium_risk_threshold": 40,
			"overdue_weight": 30,
			"late_payment_weight": 20,
			"high_outstanding_weight": 20,
			"multiple_unpaid_weight": 10,
			"unusually_large_invoice_weight": 10,
		}

		for fieldname, default_value in defaults.items():
			if self.get(fieldname) in (None, ""):
				self.set(fieldname, default_value)

	def _validate_thresholds(self):
		medium_threshold = int(self.medium_risk_threshold or 0)
		high_threshold = int(self.high_risk_threshold or 0)

		if medium_threshold < 0 or high_threshold < 0:
			frappe.throw("Risk thresholds cannot be negative.")

		if medium_threshold >= high_threshold:
			frappe.throw("Medium Risk Threshold must be lower than High Risk Threshold.")

		if high_threshold > 100:
			frappe.throw("High Risk Threshold cannot be greater than 100.")

	def _validate_weights(self):
		weight_fields = (
			"overdue_weight",
			"late_payment_weight",
			"high_outstanding_weight",
			"multiple_unpaid_weight",
			"unusually_large_invoice_weight",
		)

		for fieldname in weight_fields:
			value = int(self.get(fieldname) or 0)
			if value < 0:
				label = frappe.unscrub(fieldname)
				frappe.throw(f"{label} cannot be negative.")

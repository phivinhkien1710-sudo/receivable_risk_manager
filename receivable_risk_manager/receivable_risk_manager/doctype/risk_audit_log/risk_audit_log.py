# Copyright (c) 2026, Kien Phi and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class RiskAuditLog(Document):
	def validate(self):
		self._validate_scores()
		self._validate_levels()

	def _validate_scores(self):
		for fieldname in ("previous_score", "new_score"):
			value = self.get(fieldname)
			if value is not None and not 0 <= value <= 100:
				frappe.throw(f"{frappe.unscrub(fieldname)} must be between 0 and 100.")

	def _validate_levels(self):
		valid_levels = {"", "Low", "Medium", "High", None}
		for fieldname in ("previous_level", "new_level"):
			if self.get(fieldname) not in valid_levels:
				frappe.throw(f"{frappe.unscrub(fieldname)} must be Low, Medium, or High.")

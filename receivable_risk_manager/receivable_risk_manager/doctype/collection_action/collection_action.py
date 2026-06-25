# Copyright (c) 2026, kien and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CollectionAction(Document):
	def validate(self):
		self._set_active_invoice_key()
		self._validate_no_duplicate_active_action()

	def _set_active_invoice_key(self):
		if self.status == "Resolved":
			self.active_invoice_key = None
			return

		if self.external_invoice_id and self.action_type:
			self.active_invoice_key = f"{self.external_invoice_id}:{self.action_type}"

	def _validate_no_duplicate_active_action(self):
		if self.status == "Resolved" or not self.external_invoice_id or not self.action_type:
			return

		existing_action = frappe.db.exists(
			"Collection Action",
			{
				"external_invoice_id": self.external_invoice_id,
				"action_type": self.action_type,
				"status": ["!=", "Resolved"],
				"name": ["!=", self.name],
			},
		)

		if existing_action:
			frappe.throw(
				"An active Collection Action already exists for this invoice and action type: "
				f"{existing_action}"
			)

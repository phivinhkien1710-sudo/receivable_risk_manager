# Copyright (c) 2026, kien and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from receivable_risk_manager.services.risk_audit import log_collection_action_event


TERMINAL_STATUSES = ("Resolved", "Rejected")


class CollectionAction(Document):
	def validate(self):
		self._set_active_invoice_key()
		self._validate_no_duplicate_active_action()

	def on_update(self):
		self._log_proposal_transition()

	def _set_active_invoice_key(self):
		if self.status in TERMINAL_STATUSES:
			self.active_invoice_key = None
			return

		if self.external_invoice_id and self.action_type:
			self.active_invoice_key = f"{self.external_invoice_id}:{self.action_type}"

	def _validate_no_duplicate_active_action(self):
		if self.status in TERMINAL_STATUSES or not self.external_invoice_id or not self.action_type:
			return

		existing_action = frappe.db.exists(
			"Collection Action",
			{
				"external_invoice_id": self.external_invoice_id,
				"action_type": self.action_type,
				"status": ["not in", list(TERMINAL_STATUSES)],
				"name": ["!=", self.name],
			},
		)

		if existing_action:
			frappe.throw(
				"An active Collection Action already exists for this invoice and action type: "
				f"{existing_action}"
			)

	def _log_proposal_transition(self):
		if not self.has_value_changed("status"):
			return

		previous = self.get_doc_before_save()
		if not previous or previous.status != "Proposed":
			return

		if self.status == "Open":
			reason = f"{frappe.session.user} approved this AI-drafted collection action."
		elif self.status == "Rejected":
			reason = f"{frappe.session.user} rejected this AI-drafted collection action."
		else:
			return

		log_collection_action_event(
			collection_action_name=self.name,
			reason=reason,
			source="Manual Review",
			customer_id=self.customer_id,
			external_invoice_id=self.external_invoice_id,
		)

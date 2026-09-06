import unittest
from pathlib import Path
from unittest.mock import call, patch

from receivable_risk_manager.receivable_risk_manager.report.collection_action_queue import (
	collection_action_queue,
)
from receivable_risk_manager.services.batches import stamp_batch_on_downstream_records


class TestCollectionActionQueueFilters(unittest.TestCase):
	def test_server_builds_all_demo_route_filters(self):
		filters = collection_action_queue.build_report_filters(
			{
				"status": "Proposed",
				"receivables_import_job": "RIMJ-00035",
				"ai_review_run": "AIRV-00013",
				"disagreements_only": 1,
			}
		)

		self.assertEqual(
			filters,
			{
				"status": "Proposed",
				"receivables_import_job": "RIMJ-00035",
				"ai_review_run": "AIRV-00013",
				"ai_agreed_with_rules": 0,
			},
		)

	def test_string_zero_does_not_enable_disagreements_filter(self):
		filters = collection_action_queue.build_report_filters(
			{"status": "Proposed", "disagreements_only": "0"}
		)

		self.assertNotIn("ai_agreed_with_rules", filters)

	def test_client_declares_every_filter_used_by_form_routes(self):
		client_script = Path(collection_action_queue.__file__).with_suffix(".js").read_text()

		for fieldname in (
			"status",
			"receivables_import_job",
			"ai_review_run",
			"disagreements_only",
		):
			self.assertIn(f'fieldname: "{fieldname}"', client_script)

		self.assertIn("\\nProposed\\nOpen", client_script)

	def test_report_exposes_a_link_to_open_the_proposal(self):
		columns = collection_action_queue.get_columns()

		self.assertIn(
			{
				"label": "Collection Action",
				"fieldname": "name",
				"fieldtype": "Link",
				"options": "Collection Action",
				"width": 130,
			},
			columns,
		)


class TestBatchStamping(unittest.TestCase):
	@patch("receivable_risk_manager.services.batches.frappe")
	@patch(
		"receivable_risk_manager.services.batches.get_batch_invoice_ids",
		return_value=["INV-1"],
	)
	def test_null_downstream_batch_fields_are_stamped(self, _get_invoice_ids, frappe):
		frappe.get_all.side_effect = [[type("Row", (), {"name": "IRA-1"})()], [type("Row", (), {"name": "CA-1"})()]]

		result = stamp_batch_on_downstream_records("RIMJ-1")

		self.assertEqual(result, {"assessments_stamped": 1, "actions_stamped": 1})
		for get_all_call in frappe.get_all.call_args_list:
			self.assertEqual(
				get_all_call.kwargs["filters"]["receivables_import_job"],
				["is", "not set"],
			)
		self.assertEqual(
			frappe.db.set_value.call_args_list,
			[
				call("Invoice Risk Assessment", "IRA-1", "receivables_import_job", "RIMJ-1", update_modified=False),
				call("Collection Action", "CA-1", "receivables_import_job", "RIMJ-1", update_modified=False),
			],
		)

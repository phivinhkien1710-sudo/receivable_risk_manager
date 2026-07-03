from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from receivable_risk_manager.services.import_jobs import queue_import_job


class TestImportJobQueueing(FrappeTestCase):
	def setUp(self):
		self.job = frappe.new_doc("Receivables Import Job")
		self.job.csv_file = "/files/test-rrm-queue.csv"
		self.job.status = "Validated"
		self.job.insert(ignore_permissions=True)

	def tearDown(self):
		frappe.delete_doc(
			"Receivables Import Job", self.job.name, force=True, ignore_permissions=True
		)

	def test_queue_import_job_sets_status_and_enqueues_background_job(self):
		with patch("frappe.enqueue") as mock_enqueue:
			result = queue_import_job(self.job.name)

		self.assertEqual(result["status"], "Queued")
		self.assertTrue(result["queued"])

		self.job.reload()
		self.assertEqual(self.job.status, "Queued")

		mock_enqueue.assert_called_once()
		_, kwargs = mock_enqueue.call_args
		self.assertEqual(kwargs["receivables_import_job_name"], self.job.name)
		self.assertEqual(kwargs["queue"], "long")
		self.assertEqual(kwargs["job_id"], f"receivables-import-job-{self.job.name}")

	def test_queue_import_job_rejects_non_queueable_status(self):
		self.job.status = "Draft"
		self.job.save(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			with patch("frappe.enqueue") as mock_enqueue:
				queue_import_job(self.job.name)

		mock_enqueue.assert_not_called()

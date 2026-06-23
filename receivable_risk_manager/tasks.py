import frappe

from receivable_risk_manager.services.collection_actions import generate_collection_actions
from receivable_risk_manager.services.customer_aggregation import recalculate_receivables_customers
from receivable_risk_manager.services.customer_risk import recalculate_all_customer_risks
from receivable_risk_manager.services.invoice_risk import recalculate_all_invoice_risk_assessments


LOGGER_NAME = "receivable_risk_manager"


def run_full_recalculation():
	"""Run the full receivables risk recalculation pipeline.

	This function is safe to run manually with bench execute. It runs each major
	step in order and stops if one step raises an exception, because downstream
	steps depend on the earlier results being fresh.
	"""

	logger = frappe.logger(LOGGER_NAME)
	logger.info("Starting full receivables risk recalculation")

	summary = {
		"status": "running",
		"customer_aggregation": None,
		"customer_risk_scoring": None,
		"invoice_risk_assessment": None,
		"collection_action_generation": None,
	}

	try:
		summary["customer_aggregation"] = _run_pipeline_step(
			logger=logger,
			step_key="customer_aggregation",
			step_label="Customer aggregation",
			function=recalculate_receivables_customers,
		)

		summary["customer_risk_scoring"] = _run_pipeline_step(
			logger=logger,
			step_key="customer_risk_scoring",
			step_label="Customer risk scoring",
			function=recalculate_all_customer_risks,
		)

		summary["invoice_risk_assessment"] = _run_pipeline_step(
			logger=logger,
			step_key="invoice_risk_assessment",
			step_label="Invoice risk assessment",
			function=recalculate_all_invoice_risk_assessments,
		)

		summary["collection_action_generation"] = _run_pipeline_step(
			logger=logger,
			step_key="collection_action_generation",
			step_label="Collection action generation",
			function=generate_collection_actions,
		)

	except Exception as exc:
		summary["status"] = "failed"
		summary["failed_step"] = _get_failed_step(summary)
		summary["error"] = str(exc)

		logger.error(
			"Full receivables risk recalculation failed at step: %s",
			summary["failed_step"],
		)
		frappe.log_error(
			title="Full receivables risk recalculation failed",
			message=frappe.get_traceback(),
		)
		return summary

	summary["status"] = "completed"
	logger.info("Completed full receivables risk recalculation")
	return summary


def daily_recalculate_receivables_risk():
	"""Scheduler entrypoint for daily receivables risk recalculation."""

	logger = frappe.logger(LOGGER_NAME)
	logger.info("Starting daily receivables risk recalculation")

	result = run_full_recalculation()

	if result.get("status") == "completed":
		logger.info("Completed daily receivables risk recalculation")
	else:
		logger.error("Daily receivables risk recalculation failed")

	return result


def _run_pipeline_step(logger, step_key, step_label, function):
	logger.info("Starting step: %s", step_label)

	try:
		result = function()
	except Exception:
		logger.error("Step failed: %s", step_label)
		frappe.log_error(
			title=f"Receivables risk pipeline step failed: {step_label}",
			message=frappe.get_traceback(),
		)
		raise

	logger.info("Completed step: %s", step_label)
	return {
		"step": step_key,
		"label": step_label,
		"result": result,
	}


def _get_failed_step(summary):
	for step_key in (
		"customer_aggregation",
		"customer_risk_scoring",
		"invoice_risk_assessment",
		"collection_action_generation",
	):
		if summary.get(step_key) is None:
			return step_key

	return "unknown"

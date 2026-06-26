RISK_LEVELS = ["Low", "Medium", "High"]
AGING_BUCKETS = ["Current", "1-30", "31-60", "61-90", "90+"]


def get_aging_bucket(days_overdue):
	"""Return a readable aging bucket for a days-overdue value.

	This helper is intentionally pure so it can be tested without a Frappe site.
	"""

	days_overdue = to_int(days_overdue)

	if days_overdue <= 0:
		return "Current"
	if days_overdue <= 30:
		return "1-30"
	if days_overdue <= 60:
		return "31-60"
	if days_overdue <= 90:
		return "61-90"
	return "90+"


def get_dashboard_summary():
	"""Return headline KPIs for the receivables risk dashboard."""

	frappe = get_frappe()

	total_customers = frappe.db.count("Receivables Customer")
	high_risk_customers = frappe.db.count(
		"Receivables Customer", filters={"risk_level": "High"}
	)
	medium_high_open_invoices = frappe.db.count(
		"Invoice Risk Assessment",
		filters={
			"is_open": 1,
			"risk_level": ["in", ["Medium", "High"]],
		},
	)
	open_collection_actions = frappe.db.count(
		"Collection Action", filters={"status": ["!=", "Resolved"]}
	)
	high_priority_open_actions = frappe.db.count(
		"Collection Action",
		filters={
			"priority": "High",
			"status": ["!=", "Resolved"],
		},
	)

	return {
		"total_customers": total_customers,
		"high_risk_customers": high_risk_customers,
		"total_open_amount": get_total_open_amount(),
		"high_risk_open_amount": get_high_risk_open_amount(),
		"medium_high_open_invoices": medium_high_open_invoices,
		"open_collection_actions": open_collection_actions,
		"high_priority_open_actions": high_priority_open_actions,
	}


def get_risk_level_distribution():
	"""Return customer count grouped by risk level."""

	frappe = get_frappe()

	rows = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(risk_level, ''), 'Unclassified') AS risk_level,
		       COUNT(*) AS customer_count
		FROM `tabReceivables Customer`
		GROUP BY COALESCE(NULLIF(risk_level, ''), 'Unclassified')
		""",
		as_dict=True,
	)

	return fill_missing_levels(rows, "customer_count")


def get_outstanding_amount_by_risk_level():
	"""Return open customer exposure grouped by customer risk level."""

	frappe = get_frappe()

	rows = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(risk_level, ''), 'Unclassified') AS risk_level,
		       COALESCE(SUM(open_amount), 0) AS open_amount
		FROM `tabReceivables Customer`
		GROUP BY COALESCE(NULLIF(risk_level, ''), 'Unclassified')
		""",
		as_dict=True,
	)

	return fill_missing_levels(rows, "open_amount")


def get_aging_bucket_distribution():
	"""Return open invoice amount and count by aging bucket."""

	frappe = get_frappe()

	rows = frappe.db.sql(
		"""
		SELECT
			CASE
				WHEN COALESCE(days_overdue, 0) <= 0 THEN 'Current'
				WHEN days_overdue <= 30 THEN '1-30'
				WHEN days_overdue <= 60 THEN '31-60'
				WHEN days_overdue <= 90 THEN '61-90'
				ELSE '90+'
			END AS aging_bucket,
			COUNT(*) AS invoice_count,
			COALESCE(SUM(invoice_amount), 0) AS invoice_amount
		FROM `tabInvoice Risk Assessment`
		WHERE is_open = 1
		GROUP BY
			CASE
				WHEN COALESCE(days_overdue, 0) <= 0 THEN 'Current'
				WHEN days_overdue <= 30 THEN '1-30'
				WHEN days_overdue <= 60 THEN '31-60'
				WHEN days_overdue <= 90 THEN '61-90'
				ELSE '90+'
			END
		""",
		as_dict=True,
	)

	by_bucket = {row.aging_bucket: row for row in rows}
	result = []

	for bucket in AGING_BUCKETS:
		row = by_bucket.get(bucket)
		result.append(
			{
				"aging_bucket": bucket,
				"invoice_count": int(row.invoice_count or 0) if row else 0,
				"invoice_amount": float(row.invoice_amount or 0) if row else 0,
			}
		)

	return result


def get_top_risky_customers(limit=10):
	"""Return the highest-risk customers, using exposure as the tiebreaker."""

	frappe = get_frappe()
	limit = max(1, min(to_int(limit) or 10, 50))

	return frappe.get_all(
		"Receivables Customer",
		fields=[
			"customer_id",
			"customer_name",
			"risk_level",
			"risk_score",
			"risk_confidence",
			"open_amount",
			"open_invoice_count",
			"late_payment_rate",
			"average_payment_delay",
		],
		order_by="risk_score desc, open_amount desc",
		limit_page_length=limit,
	)


def get_collection_actions_by_status():
	"""Return collection action count grouped by workflow status."""

	frappe = get_frappe()

	rows = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(status, ''), 'Unclassified') AS status,
		       COUNT(*) AS action_count
		FROM `tabCollection Action`
		GROUP BY COALESCE(NULLIF(status, ''), 'Unclassified')
		ORDER BY action_count DESC
		""",
		as_dict=True,
	)

	return [
		{
			"status": row.status,
			"action_count": int(row.action_count or 0),
		}
		for row in rows
	]


def get_monthly_overdue_trend():
	"""Return open overdue exposure grouped by due month.

	The source dataset is historical, so this is not a live monthly snapshot.
	It should be read as currently open overdue exposure grouped by due month.
	"""

	frappe = get_frappe()

	rows = frappe.db.sql(
		"""
		SELECT DATE_FORMAT(due_date, '%Y-%m') AS due_month,
		       COUNT(*) AS invoice_count,
		       COALESCE(SUM(invoice_amount), 0) AS invoice_amount
		FROM `tabInvoice Risk Assessment`
		WHERE is_open = 1
		  AND COALESCE(days_overdue, 0) > 0
		  AND due_date IS NOT NULL
		GROUP BY DATE_FORMAT(due_date, '%Y-%m')
		ORDER BY due_month ASC
		""",
		as_dict=True,
	)

	return [
		{
			"due_month": row.due_month,
			"invoice_count": int(row.invoice_count or 0),
			"invoice_amount": float(row.invoice_amount or 0),
		}
		for row in rows
	]


def get_total_open_amount():
	return get_single_value(
		"""
		SELECT COALESCE(SUM(open_amount), 0)
		FROM `tabReceivables Customer`
		"""
	)


def get_high_risk_open_amount():
	return get_single_value(
		"""
		SELECT COALESCE(SUM(open_amount), 0)
		FROM `tabReceivables Customer`
		WHERE risk_level = 'High'
		"""
	)


def fill_missing_levels(rows, value_fieldname):
	by_level = {get_row_value(row, "risk_level"): row for row in rows}
	result = []

	for level in RISK_LEVELS:
		row = by_level.get(level)
		value = get_row_value(row, value_fieldname) if row else 0
		result.append(
			{
				"risk_level": level,
				value_fieldname: float(value or 0)
				if value_fieldname.endswith("amount")
				else int(value or 0),
			}
		)

	for row in rows:
		risk_level = get_row_value(row, "risk_level")
		if risk_level not in RISK_LEVELS:
			value = get_row_value(row, value_fieldname)
			result.append(
				{
					"risk_level": risk_level,
					value_fieldname: float(value or 0)
					if value_fieldname.endswith("amount")
					else int(value or 0),
				}
			)

	return result


def get_single_value(query):
	frappe = get_frappe()
	result = frappe.db.sql(query)
	return float(result[0][0] or 0) if result else 0


def get_frappe():
	import frappe

	return frappe


def get_row_value(row, fieldname):
	if isinstance(row, dict):
		return row.get(fieldname)

	return getattr(row, fieldname, None)


def to_int(value):
	try:
		return int(value or 0)
	except (TypeError, ValueError):
		return 0

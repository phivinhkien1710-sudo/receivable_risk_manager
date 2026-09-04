import frappe
from frappe.model.document import Document


class ReceivablesBatchMember(Document):
	"""Immutable membership between a Receivables Import Job and one Receivables
	Invoice it brought in.

	Deliberately a join doctype rather than a single `receivables_import_job`
	field on Receivables Invoice: invoices get updated by later imports (the
	import job's own `invoices_updated` counter exists for exactly that case),
	and a single field would be overwritten on re-import, silently emptying the
	older batch. Membership has to survive re-import for "process only today's
	batch" to keep meaning the same thing a week later.
	"""

	pass

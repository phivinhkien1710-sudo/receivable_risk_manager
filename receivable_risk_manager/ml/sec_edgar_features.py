"""Feature extraction helpers for SEC EDGAR company facts.

The SEC ``companyfacts`` files are company-level financial disclosures, not
invoice-level receivables records. These helpers intentionally produce
company-level enrichment features that can later be matched to Receivables
Customer records.
"""

from __future__ import annotations

from datetime import date, datetime


FINANCIAL_CONCEPTS = {
	"revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
	"cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
	"assets_current": ["AssetsCurrent"],
	"liabilities_current": ["LiabilitiesCurrent"],
	"assets": ["Assets"],
	"liabilities": ["Liabilities"],
	"equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
	"accounts_payable": ["AccountsPayableCurrent", "AccountsPayableAndAccruedLiabilitiesCurrent"],
	"operating_income": ["OperatingIncomeLoss"],
	"net_income": ["NetIncomeLoss", "ProfitLoss"],
}

DEFAULT_FORMS = {"10-K", "10-Q", "20-F", "40-F"}


def build_sec_company_profile(companyfacts):
	"""Return one normalized company-level financial profile from SEC companyfacts JSON."""

	profile = {
		"cik": normalize_cik(companyfacts.get("cik")),
		"entity_name": companyfacts.get("entityName") or companyfacts.get("entity_name"),
		"sic": companyfacts.get("sic"),
		"sic_description": companyfacts.get("sicDescription"),
	}

	latest_filed_date = None
	latest_fiscal_end = None

	for feature_name, concept_names in FINANCIAL_CONCEPTS.items():
		fact = extract_latest_numeric_fact(companyfacts, concept_names)
		profile[feature_name] = fact["value"]
		profile[f"{feature_name}_filed"] = fact["filed"]
		profile[f"{feature_name}_period_end"] = fact["end"]

		latest_filed_date = max_optional_date(latest_filed_date, fact["filed"])
		latest_fiscal_end = max_optional_date(latest_fiscal_end, fact["end"])

	profile["latest_filed_date"] = latest_filed_date
	profile["latest_fiscal_period_end"] = latest_fiscal_end
	profile["current_ratio"] = safe_divide(profile["assets_current"], profile["liabilities_current"])
	profile["cash_to_current_liabilities"] = safe_divide(profile["cash"], profile["liabilities_current"])
	profile["liabilities_to_assets"] = safe_divide(profile["liabilities"], profile["assets"])
	profile["accounts_payable_to_revenue"] = safe_divide(profile["accounts_payable"], profile["revenue"])
	profile["net_margin"] = safe_divide(profile["net_income"], profile["revenue"])
	profile["sec_financial_risk_band"] = assign_sec_financial_risk_band(profile)

	return profile


def extract_latest_numeric_fact(companyfacts, concept_names, unit="USD", allowed_forms=None):
	"""Find the newest usable fact for the first available concept in a concept list."""

	allowed_forms = allowed_forms or DEFAULT_FORMS

	for concept_name in concept_names:
		facts = get_concept_facts(companyfacts, concept_name, unit=unit)
		latest_fact = choose_latest_fact(facts, allowed_forms=allowed_forms)

		if latest_fact:
			return {
				"concept": concept_name,
				"value": to_float_or_none(latest_fact.get("val")),
				"filed": latest_fact.get("filed"),
				"end": latest_fact.get("end"),
				"form": latest_fact.get("form"),
			}

	return {
		"concept": None,
		"value": None,
		"filed": None,
		"end": None,
		"form": None,
	}


def get_concept_facts(companyfacts, concept_name, unit="USD"):
	"""Return SEC fact rows for a US-GAAP concept/unit pair."""

	facts = companyfacts.get("facts", {})
	us_gaap = facts.get("us-gaap", {})
	concept = us_gaap.get(concept_name, {})
	units = concept.get("units", {})

	return units.get(unit, [])


def choose_latest_fact(facts, allowed_forms=None):
	"""Choose the most recent numeric SEC fact by filed date, then period end date."""

	allowed_forms = allowed_forms or DEFAULT_FORMS
	usable_facts = []

	for fact in facts:
		if allowed_forms and fact.get("form") not in allowed_forms:
			continue
		if to_float_or_none(fact.get("val")) is None:
			continue
		if not fact.get("filed") and not fact.get("end"):
			continue

		usable_facts.append(fact)

	if not usable_facts:
		return None

	return sorted(
		usable_facts,
		key=lambda fact: (
			parse_date_or_min(fact.get("filed")),
			parse_date_or_min(fact.get("end")),
		),
		reverse=True,
	)[0]


def assign_sec_financial_risk_band(profile):
	"""Assign a simple explainable financial-risk band from company financial ratios."""

	current_ratio = to_float_or_none(profile.get("current_ratio"))
	cash_to_current_liabilities = to_float_or_none(profile.get("cash_to_current_liabilities"))
	liabilities_to_assets = to_float_or_none(profile.get("liabilities_to_assets"))
	net_margin = to_float_or_none(profile.get("net_margin"))

	high_risk_signals = 0
	medium_risk_signals = 0

	if current_ratio is not None:
		if current_ratio < 1:
			high_risk_signals += 1
		elif current_ratio < 1.5:
			medium_risk_signals += 1

	if cash_to_current_liabilities is not None:
		if cash_to_current_liabilities < 0.1:
			high_risk_signals += 1
		elif cash_to_current_liabilities < 0.25:
			medium_risk_signals += 1

	if liabilities_to_assets is not None:
		if liabilities_to_assets > 0.9:
			high_risk_signals += 1
		elif liabilities_to_assets > 0.7:
			medium_risk_signals += 1

	if net_margin is not None:
		if net_margin < -0.1:
			high_risk_signals += 1
		elif net_margin < 0:
			medium_risk_signals += 1

	if high_risk_signals >= 2:
		return "High"
	if high_risk_signals == 1 or medium_risk_signals >= 2:
		return "Medium"
	if medium_risk_signals == 1:
		return "Low"

	return "Unknown" if has_no_ratio_data(profile) else "Low"


def has_no_ratio_data(profile):
	return all(
		profile.get(field) is None
		for field in (
			"current_ratio",
			"cash_to_current_liabilities",
			"liabilities_to_assets",
			"net_margin",
		)
	)


def normalize_cik(value):
	if value is None:
		return None

	try:
		return str(int(value)).zfill(10)
	except (TypeError, ValueError):
		return str(value).strip().zfill(10)


def safe_divide(numerator, denominator):
	numerator = to_float_or_none(numerator)
	denominator = to_float_or_none(denominator)

	if numerator is None or denominator in (None, 0):
		return None

	return round(numerator / denominator, 6)


def to_float_or_none(value):
	if value is None:
		return None

	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def max_optional_date(current_value, candidate_value):
	if not candidate_value:
		return current_value

	if current_value is None:
		return candidate_value

	return candidate_value if parse_date_or_min(candidate_value) > parse_date_or_min(current_value) else current_value


def parse_date_or_min(value):
	if isinstance(value, date):
		return value

	if not value:
		return date.min

	try:
		return datetime.strptime(str(value), "%Y-%m-%d").date()
	except ValueError:
		return date.min

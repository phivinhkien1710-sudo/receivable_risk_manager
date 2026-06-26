import unittest

import pandas as pd

from receivable_risk_manager.ml.train_public_payment_model import (
	FEATURE_COLUMNS,
	LEAKAGE_COLUMNS,
	build_training_summary,
	prepare_training_data,
	validate_feature_list,
)


class TestTrainPublicPaymentModel(unittest.TestCase):
	def test_feature_list_excludes_leakage_columns(self):
		validate_feature_list()
		self.assertFalse(set(FEATURE_COLUMNS).intersection(LEAKAGE_COLUMNS))

	def test_prepare_training_data_drops_missing_target_and_company(self):
		df = build_sample_training_dataframe()
		df.loc[0, "slow_payer_label"] = pd.NA
		df.loc[1, "company_number"] = pd.NA

		x, y, groups = prepare_training_data(df)

		self.assertEqual(len(x), 2)
		self.assertEqual(len(y), 2)
		self.assertEqual(len(groups), 2)
		self.assertNotIn("avg_days_to_pay", x.columns)

	def test_build_training_summary_reports_group_overlap(self):
		df = build_sample_training_dataframe()
		_, y, _ = prepare_training_data(df)
		results = {
			"logistic_regression": {
				"metrics": {
					"accuracy": 0.8,
					"precision": 0.7,
					"recall": 0.6,
					"f1": 0.65,
					"roc_auc": 0.75,
				}
			}
		}

		summary = build_training_summary(
			df,
			y,
			pd.Series(["00000001", "00000002"]),
			pd.Series(["00000003", "00000004"]),
			results,
			"logistic_regression",
		)

		self.assertEqual(summary["group_overlap"], 0)
		self.assertEqual(summary["best_model"], "logistic_regression")
		self.assertEqual(summary["positive_label_count"], 2)


def build_sample_training_dataframe():
	rows = []
	for index in range(4):
		rows.append(
			{
				"company_number": f"0000000{index + 1}",
				"slow_payer_label": index % 2,
				"avg_days_to_pay": 70 if index % 2 else 20,
				"pct_paid_within_30": 50,
				"pct_paid_31_60": 30,
				"pct_paid_later_60": 20,
				"pct_not_paid_within_terms": 10,
				"pct_not_paid_due_to_dispute": 1,
				"shortest_standard_payment_period": 30,
				"longest_standard_payment_period": 60,
				"maximum_contractual_payment_period": 90,
				"company_reporting_count": 2,
				"payment_terms_changed_flag": "No",
				"payment_terms_changed_covid_related": 0,
				"payment_terms_changed_policy_related": 0,
				"payment_terms_changed_supplier_related": 0,
				"e_invoicing_offered": "Yes",
				"supply_chain_financing_offered": "No",
				"participates_in_payment_codes": "No",
			}
		)

	return pd.DataFrame(rows)


if __name__ == "__main__":
	unittest.main()

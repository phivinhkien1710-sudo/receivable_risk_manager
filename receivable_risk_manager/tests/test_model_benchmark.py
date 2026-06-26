import unittest

import pandas as pd

from receivable_risk_manager.ml.model_benchmark import (
	REQUIRED_RESULT_FIELDS,
	build_model_registry,
	build_skipped_result,
	calculate_default_metrics,
	select_final_model,
)
from receivable_risk_manager.ml.train_public_payment_model import (
	FEATURE_COLUMNS,
	GROUP_COLUMN,
	LEAKAGE_COLUMNS,
	split_train_test_by_company,
)


class TestModelBenchmark(unittest.TestCase):
	def test_model_registry_includes_expected_models_and_skips_optional(self):
		registry = build_model_registry(random_state=42)

		for model_name in (
			"dummy_majority",
			"logistic_regression_balanced",
			"sgd_log_loss_balanced",
			"ridge_classifier_balanced",
			"decision_tree_balanced",
			"random_forest_balanced",
			"extra_trees_balanced",
			"linear_svc_balanced",
		):
			self.assertIn(model_name, registry)

		self.assertIn("xgboost", registry)
		self.assertTrue("skip_reason" in registry["xgboost"] or "estimator" in registry["xgboost"])
		self.assertTrue("skip_reason" in registry["lightgbm"] or "estimator" in registry["lightgbm"])
		self.assertTrue("skip_reason" in registry["catboost"] or "estimator" in registry["catboost"])

	def test_feature_list_excludes_identifiers_and_leakage(self):
		for column in ("company_name", "company_number", "report_id", "source_url"):
			self.assertNotIn(column, FEATURE_COLUMNS)

		self.assertFalse(set(FEATURE_COLUMNS).intersection(LEAKAGE_COLUMNS))

	def test_company_split_has_zero_overlap(self):
		x = pd.DataFrame({"feature": range(10)})
		y = pd.Series([0, 1] * 5)
		groups = pd.Series([f"company-{index}" for index in range(10)], name=GROUP_COLUMN)

		split = split_train_test_by_company(x, y, groups, test_size=0.3, random_state=42)

		overlap = set(split["train_groups"]).intersection(set(split["test_groups"]))
		self.assertEqual(len(overlap), 0)

	def test_calculate_default_metrics_schema(self):
		metrics = calculate_default_metrics(
			pd.Series([0, 0, 1, 1]),
			pd.Series([0, 1, 1, 1]),
			score_values=[0.1, 0.6, 0.8, 0.9],
			probabilities=[0.1, 0.6, 0.8, 0.9],
		)

		for field in ("accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc", "brier_score"):
			self.assertIn(field, metrics)

		self.assertEqual(metrics["true_positive"], 2)
		self.assertEqual(metrics["false_positive"], 1)

	def test_select_final_model_keeps_logistic_without_meaningful_improvement(self):
		result_df = pd.DataFrame(
			[
				{
					"model_name": "logistic_regression_balanced",
					"status": "trained",
					"precision": 0.61,
					"recall": 0.81,
					"f1": 0.697,
					"roc_auc": 0.96,
					"pr_auc": 0.75,
					"brier_score": 0.07,
					"selected_threshold": 0.75,
				},
				{
					"model_name": "extra_trees_balanced",
					"status": "trained",
					"precision": 0.62,
					"recall": 0.81,
					"f1": 0.705,
					"roc_auc": 0.96,
					"pr_auc": 0.76,
					"brier_score": 0.08,
					"selected_threshold": 0.7,
				},
			]
		)

		selection = select_final_model(result_df, min_f1_improvement=0.02)

		self.assertEqual(selection["selected_model"], "logistic_regression_balanced")
		self.assertEqual(selection["selection_reason"], "kept_logistic_regression_due_to_insufficient_improvement")

	def test_skipped_result_has_required_schema_fields_after_dataframe_normalization(self):
		row = build_skipped_result("knn", "too slow")
		result_df = pd.DataFrame([row])
		for field in REQUIRED_RESULT_FIELDS:
			if field not in result_df.columns:
				result_df[field] = None

		self.assertEqual(set(REQUIRED_RESULT_FIELDS), set(result_df.columns))
		self.assertEqual(result_df.loc[0, "status"], "skipped")


if __name__ == "__main__":
	unittest.main()

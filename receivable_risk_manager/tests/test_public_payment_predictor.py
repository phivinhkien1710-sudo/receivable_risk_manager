import unittest

import pandas as pd

from receivable_risk_manager.ml.public_payment_predictor import (
	assign_prediction_risk_band,
	predict_public_payment_risk,
)
from receivable_risk_manager.ml.train_public_payment_model import FEATURE_COLUMNS, build_models


class TestPublicPaymentPredictor(unittest.TestCase):
	def test_prediction_output_schema_and_explanations(self):
		model = build_fitted_logistic_model()
		features = build_feature_row()

		result = predict_public_payment_risk(
			features,
			model=model,
			threshold_config={"selected_threshold": 0.5},
			model_path="memory://test-model",
		)

		self.assertIn("probability", result)
		self.assertGreaterEqual(result["probability"], 0)
		self.assertLessEqual(result["probability"], 1)
		self.assertIn("predicted_label", result)
		self.assertIn("risk_band", result)
		self.assertIn("top_positive_drivers", result)
		self.assertIn("top_negative_drivers", result)
		self.assertIn("feature_snapshot", result)
		self.assertEqual(result["explanation_type"], "local_linear_contribution")
		self.assertGreater(len(result["top_positive_drivers"]), 0)

	def test_tree_model_returns_global_feature_importance_explanation(self):
		model = build_fitted_random_forest_model()
		features = build_feature_row()

		result = predict_public_payment_risk(
			features,
			model=model,
			threshold_config={"selected_threshold": 0.5},
			model_path="memory://test-random-forest",
		)

		self.assertEqual(result["explanation_type"], "global_feature_importance")
		self.assertGreater(len(result["top_positive_drivers"]), 0)

	def test_unknown_categorical_values_do_not_crash(self):
		model = build_fitted_logistic_model()
		features = build_feature_row()
		features["payment_terms_changed_flag"] = "Unexpected future category"

		result = predict_public_payment_risk(
			features,
			model=model,
			threshold_config={"selected_threshold": 0.5},
			model_path="memory://test-model",
		)

		self.assertIn("probability", result)

	def test_assign_prediction_risk_band(self):
		self.assertEqual(assign_prediction_risk_band(0.8, 0.5), "High")
		self.assertEqual(assign_prediction_risk_band(0.4, 0.5), "Medium")
		self.assertEqual(assign_prediction_risk_band(0.1, 0.5), "Low")


def build_fitted_logistic_model():
	model = build_models(random_state=42)["logistic_regression"]
	x = pd.DataFrame(
		[
			build_feature_row(pct_paid_later_60=5, pct_not_paid_within_terms=5),
			build_feature_row(pct_paid_later_60=10, pct_not_paid_within_terms=10),
			build_feature_row(pct_paid_later_60=50, pct_not_paid_within_terms=35),
			build_feature_row(pct_paid_later_60=70, pct_not_paid_within_terms=45),
		],
		columns=FEATURE_COLUMNS,
	)
	y = pd.Series([0, 0, 1, 1])
	model.fit(x, y)
	return model


def build_fitted_random_forest_model():
	from sklearn.ensemble import RandomForestClassifier
	from sklearn.pipeline import Pipeline

	from receivable_risk_manager.ml.train_public_payment_model import build_preprocessor

	model = Pipeline(
		steps=[
			("preprocessor", build_preprocessor()),
			(
				"model",
				RandomForestClassifier(
					n_estimators=20,
					min_samples_leaf=1,
					random_state=42,
				),
			),
		]
	)
	x = pd.DataFrame(
		[
			build_feature_row(pct_paid_later_60=5, pct_not_paid_within_terms=5),
			build_feature_row(pct_paid_later_60=10, pct_not_paid_within_terms=10),
			build_feature_row(pct_paid_later_60=50, pct_not_paid_within_terms=35),
			build_feature_row(pct_paid_later_60=70, pct_not_paid_within_terms=45),
			build_feature_row(pct_paid_later_60=80, pct_not_paid_within_terms=55),
			build_feature_row(pct_paid_later_60=2, pct_not_paid_within_terms=1),
		],
		columns=FEATURE_COLUMNS,
	)
	y = pd.Series([0, 0, 1, 1, 1, 0])
	model.fit(x, y)
	return model


def build_feature_row(pct_paid_later_60=50, pct_not_paid_within_terms=30):
	return {
		"pct_paid_within_30": 40,
		"pct_paid_31_60": 30,
		"pct_paid_later_60": pct_paid_later_60,
		"pct_not_paid_within_terms": pct_not_paid_within_terms,
		"pct_not_paid_due_to_dispute": 1,
		"shortest_standard_payment_period": 30,
		"longest_standard_payment_period": 60,
		"maximum_contractual_payment_period": 90,
		"company_reporting_count": 3,
		"payment_terms_changed_flag": "No",
		"payment_terms_changed_covid_related": 0,
		"payment_terms_changed_policy_related": 0,
		"payment_terms_changed_supplier_related": 0,
		"e_invoicing_offered": "Yes",
		"supply_chain_financing_offered": "No",
		"participates_in_payment_codes": "No",
	}


if __name__ == "__main__":
	unittest.main()

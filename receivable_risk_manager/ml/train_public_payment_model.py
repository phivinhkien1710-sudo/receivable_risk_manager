"""Train baseline models on GOV.UK public payment behavior data.

This module trains an offline prototype model. It does not write to Frappe
DocTypes and should not run inside a Desk request.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from receivable_risk_manager.ml.public_payment_thresholds import (
	calculate_calibration_metrics,
	evaluate_probability_thresholds,
	export_json,
	export_threshold_report,
	select_recommended_threshold,
)


TARGET_COLUMN = "slow_payer_label"
GROUP_COLUMN = "company_number"

NUMERIC_FEATURES = [
	"pct_paid_within_30",
	"pct_paid_31_60",
	"pct_paid_later_60",
	"pct_not_paid_within_terms",
	"pct_not_paid_due_to_dispute",
	"shortest_standard_payment_period",
	"longest_standard_payment_period",
	"maximum_contractual_payment_period",
	"company_reporting_count",
	"payment_terms_changed_covid_related",
	"payment_terms_changed_policy_related",
	"payment_terms_changed_supplier_related",
]

CATEGORICAL_FEATURES = [
	"payment_terms_changed_flag",
	"e_invoicing_offered",
	"supply_chain_financing_offered",
	"participates_in_payment_codes",
]

FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES

LEAKAGE_COLUMNS = {
	"avg_days_to_pay",
	"slow_payer_label",
	"late_terms_label",
	"payment_speed_score",
	"payment_behavior_score",
	"public_payment_risk_band",
}


def load_ml_ready_data(input_path):
	"""Load the ML-ready public payment dataset."""

	return pd.read_csv(input_path, dtype={GROUP_COLUMN: str})


def prepare_training_data(df):
	"""Return model features, target labels, and company groups.

	Rows without a target label or company number are dropped. The target is
	``slow_payer_label`` and the direct source column ``avg_days_to_pay`` is not
	used as a feature to avoid leakage.
	"""

	validate_feature_list()

	required_columns = [GROUP_COLUMN, TARGET_COLUMN, *FEATURE_COLUMNS]
	missing_columns = [column for column in required_columns if column not in df.columns]
	if missing_columns:
		raise ValueError(f"Missing required training columns: {', '.join(missing_columns)}")

	result = df[required_columns].copy()
	result = result.dropna(subset=[GROUP_COLUMN, TARGET_COLUMN])
	result[TARGET_COLUMN] = pd.to_numeric(result[TARGET_COLUMN], errors="coerce")
	result = result.dropna(subset=[TARGET_COLUMN])
	result[TARGET_COLUMN] = result[TARGET_COLUMN].astype(int)

	x = result[FEATURE_COLUMNS].copy()
	y = result[TARGET_COLUMN].copy()
	groups = result[GROUP_COLUMN].copy()

	return x, y, groups


def validate_feature_list():
	"""Guard against accidental target leakage in future edits."""

	leaky_features = sorted(set(FEATURE_COLUMNS).intersection(LEAKAGE_COLUMNS))
	if leaky_features:
		raise ValueError(f"Feature list contains leakage columns: {', '.join(leaky_features)}")


def split_train_test_by_company(x, y, groups, test_size=0.2, random_state=42):
	"""Split rows by company so no company appears in both train and test."""

	from sklearn.model_selection import GroupShuffleSplit

	splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
	train_index, test_index = next(splitter.split(x, y, groups=groups))

	return {
		"x_train": x.iloc[train_index],
		"x_test": x.iloc[test_index],
		"y_train": y.iloc[train_index],
		"y_test": y.iloc[test_index],
		"train_groups": groups.iloc[train_index],
		"test_groups": groups.iloc[test_index],
	}


def build_models(random_state=42):
	"""Build baseline models with the same preprocessing pipeline."""

	from sklearn.ensemble import RandomForestClassifier
	from sklearn.linear_model import LogisticRegression
	from sklearn.pipeline import Pipeline

	return {
		"logistic_regression": Pipeline(
			steps=[
				("preprocessor", build_preprocessor()),
				(
					"model",
					LogisticRegression(
						max_iter=1000,
						class_weight="balanced",
						random_state=random_state,
					),
				),
			]
		),
		"random_forest": Pipeline(
			steps=[
				("preprocessor", build_preprocessor()),
				(
					"model",
					RandomForestClassifier(
						n_estimators=200,
						min_samples_leaf=10,
						class_weight="balanced",
						random_state=random_state,
						n_jobs=-1,
					),
				),
			]
		),
	}


def build_preprocessor():
	"""Build a fresh preprocessing pipeline for one model."""

	from sklearn.compose import ColumnTransformer
	from sklearn.impute import SimpleImputer
	from sklearn.pipeline import Pipeline
	from sklearn.preprocessing import OneHotEncoder, StandardScaler

	numeric_pipeline = Pipeline(
		steps=[
			("imputer", SimpleImputer(strategy="median")),
			("scaler", StandardScaler()),
		]
	)
	categorical_pipeline = Pipeline(
		steps=[
			("imputer", SimpleImputer(strategy="most_frequent")),
			("onehot", OneHotEncoder(handle_unknown="ignore")),
		]
	)

	return ColumnTransformer(
		transformers=[
			("numeric", numeric_pipeline, NUMERIC_FEATURES),
			("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
		]
	)


def train_and_evaluate_models(x_train, y_train, x_test, y_test, random_state=42):
	"""Train baseline models and return fitted models plus metrics."""

	models = build_models(random_state=random_state)
	results = {}

	for model_name, model in models.items():
		model.fit(x_train, y_train)
		results[model_name] = {
			"model": model,
			"metrics": evaluate_model(model, x_test, y_test),
		}

	return results


def evaluate_model(model, x_test, y_test):
	"""Return classification metrics for one fitted model."""

	from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score

	predictions = model.predict(x_test)
	probabilities = get_positive_class_probabilities(model, x_test)

	metrics = {
		"accuracy": round(float(accuracy_score(y_test, predictions)), 4),
		"precision": round(float(precision_score(y_test, predictions, zero_division=0)), 4),
		"recall": round(float(recall_score(y_test, predictions, zero_division=0)), 4),
		"f1": round(float(f1_score(y_test, predictions, zero_division=0)), 4),
	}

	if probabilities is not None and y_test.nunique() == 2:
		metrics["roc_auc"] = round(float(roc_auc_score(y_test, probabilities)), 4)
	else:
		metrics["roc_auc"] = None

	return metrics


def get_positive_class_probabilities(model, x_test):
	if not hasattr(model, "predict_proba"):
		return None

	probabilities = model.predict_proba(x_test)
	if probabilities.shape[1] < 2:
		return None

	return probabilities[:, 1]


def choose_best_model(results):
	"""Choose the best model by F1 score, then ROC AUC."""

	return sorted(
		results,
		key=lambda model_name: (
			results[model_name]["metrics"].get("f1") or 0,
			results[model_name]["metrics"].get("roc_auc") or 0,
		),
		reverse=True,
	)[0]


def build_training_summary(
	df,
	y,
	train_groups,
	test_groups,
	results,
	best_model_name,
	threshold_config=None,
	calibration_metrics=None,
):
	"""Build a JSON-serializable training summary."""

	train_company_set = set(train_groups.dropna())
	test_company_set = set(test_groups.dropna())

	summary = {
		"target": TARGET_COLUMN,
		"features": FEATURE_COLUMNS,
		"leakage_columns_excluded": sorted(LEAKAGE_COLUMNS),
		"rows_available": int(len(df)),
		"rows_used": int(len(y)),
		"positive_label_count": int((y == 1).sum()),
		"negative_label_count": int((y == 0).sum()),
		"positive_label_rate": round(float((y == 1).mean()), 4),
		"train_companies": len(train_company_set),
		"test_companies": len(test_company_set),
		"group_overlap": len(train_company_set.intersection(test_company_set)),
		"models": {model_name: result["metrics"] for model_name, result in results.items()},
		"best_model": best_model_name,
	}

	if threshold_config:
		summary["threshold_config"] = threshold_config
	if calibration_metrics:
		summary["calibration_metrics"] = calibration_metrics

	return summary


def export_training_artifacts(
	results,
	best_model_name,
	summary,
	output_dir,
	threshold_report=None,
	threshold_config=None,
	calibration_metrics=None,
	threshold_report_path="ml/data/processed/public_payment_threshold_report.csv",
):
	"""Persist model, metrics, training columns, and feature importance."""

	import joblib

	output_path = Path(output_dir)
	output_path.mkdir(parents=True, exist_ok=True)

	best_model = results[best_model_name]["model"]
	model_path = output_path / "public_payment_model.joblib"
	metrics_path = output_path / "model_metrics.json"
	columns_path = output_path / "training_columns.json"
	feature_importance_path = output_path / "feature_importance.csv"
	threshold_config_path = output_path / "threshold_config.json"
	calibration_metrics_path = output_path / "calibration_metrics.json"

	joblib.dump(best_model, model_path)
	metrics_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
	columns_path.write_text(json.dumps(FEATURE_COLUMNS, indent=2), encoding="utf-8")

	feature_importance = extract_feature_importance(best_model, best_model_name)
	feature_importance.to_csv(feature_importance_path, index=False)

	artifact_paths = {
		"model_path": str(model_path),
		"metrics_path": str(metrics_path),
		"training_columns_path": str(columns_path),
		"feature_importance_path": str(feature_importance_path),
	}

	if threshold_report is not None:
		path = export_threshold_report(threshold_report, threshold_report_path)
		artifact_paths["threshold_report_path"] = str(path)
	if threshold_config is not None:
		path = export_json(threshold_config, threshold_config_path)
		artifact_paths["threshold_config_path"] = str(path)
	if calibration_metrics is not None:
		path = export_json(calibration_metrics, calibration_metrics_path)
		artifact_paths["calibration_metrics_path"] = str(path)

	return artifact_paths


def extract_feature_importance(model, model_name):
	"""Return feature importance or coefficients for a fitted pipeline."""

	preprocessor = model.named_steps["preprocessor"]
	classifier = model.named_steps["model"]
	feature_names = preprocessor.get_feature_names_out()

	if hasattr(classifier, "feature_importances_"):
		values = classifier.feature_importances_
		value_column = "importance"
	elif hasattr(classifier, "coef_"):
		values = classifier.coef_[0]
		value_column = "coefficient"
	else:
		values = []
		value_column = "value"

	result = pd.DataFrame(
		{
			"model": model_name,
			"feature": feature_names,
			value_column: values,
		}
	)

	sort_column = value_column
	if value_column == "coefficient":
		result["absolute_coefficient"] = result[value_column].abs()
		sort_column = "absolute_coefficient"

	return result.sort_values(sort_column, ascending=False)


def train_public_payment_model(
	input_path="ml/data/processed/public_payment_ml_ready.csv",
	output_dir="ml/artifacts/public_payment_model",
	threshold_report_path="ml/data/processed/public_payment_threshold_report.csv",
	test_size=0.2,
	random_state=42,
	recall_floor=0.8,
):
	"""Train baseline public payment behavior models and save artifacts."""

	df = load_ml_ready_data(input_path)
	x, y, groups = prepare_training_data(df)
	split = split_train_test_by_company(
		x,
		y,
		groups,
		test_size=test_size,
		random_state=random_state,
	)

	results = train_and_evaluate_models(
		split["x_train"],
		split["y_train"],
		split["x_test"],
		split["y_test"],
		random_state=random_state,
	)
	best_model_name = choose_best_model(results)
	best_model = results[best_model_name]["model"]
	best_model_probabilities = get_positive_class_probabilities(best_model, split["x_test"])
	threshold_report = evaluate_probability_thresholds(split["y_test"], best_model_probabilities)
	threshold_config = select_recommended_threshold(threshold_report, recall_floor=recall_floor)
	calibration_metrics = calculate_calibration_metrics(split["y_test"], best_model_probabilities)
	summary = build_training_summary(
		df,
		y,
		split["train_groups"],
		split["test_groups"],
		results,
		best_model_name,
		threshold_config=threshold_config,
		calibration_metrics=calibration_metrics,
	)
	artifact_paths = export_training_artifacts(
		results,
		best_model_name,
		summary,
		output_dir,
		threshold_report=threshold_report,
		threshold_config=threshold_config,
		calibration_metrics=calibration_metrics,
		threshold_report_path=threshold_report_path,
	)

	return {
		**summary,
		"artifact_paths": artifact_paths,
	}


def train_baseline_model():
	"""Backward-compatible wrapper for earlier README/planning references."""

	return train_public_payment_model()


def main():
	parser = argparse.ArgumentParser(description="Train a baseline public payment behavior model.")
	parser.add_argument(
		"--input",
		default="ml/data/processed/public_payment_ml_ready.csv",
		help="Path to ML-ready GOV.UK public payment CSV.",
	)
	parser.add_argument(
		"--output-dir",
		default="ml/artifacts/public_payment_model",
		help="Directory where model artifacts should be written.",
	)
	parser.add_argument(
		"--threshold-report",
		default="ml/data/processed/public_payment_threshold_report.csv",
		help="Output CSV path for threshold tuning metrics.",
	)
	parser.add_argument("--test-size", type=float, default=0.2, help="Share of companies held out for testing.")
	parser.add_argument("--random-state", type=int, default=42, help="Random seed for repeatable training.")
	parser.add_argument("--recall-floor", type=float, default=0.8, help="Minimum recall preferred during threshold selection.")

	args = parser.parse_args()
	summary = train_public_payment_model(
		input_path=args.input,
		output_dir=args.output_dir,
		threshold_report_path=args.threshold_report,
		test_size=args.test_size,
		random_state=args.random_state,
		recall_floor=args.recall_floor,
	)
	print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
	main()

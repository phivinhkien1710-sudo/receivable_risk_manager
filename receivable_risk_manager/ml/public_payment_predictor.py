"""Prediction and explanation helpers for the public payment risk model."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from receivable_risk_manager.ml.train_public_payment_model import FEATURE_COLUMNS


DEFAULT_MODEL_PATH = "ml/artifacts/public_payment_model/best_model.joblib"
DEFAULT_THRESHOLD_CONFIG_PATH = "ml/artifacts/public_payment_model/selected_threshold.json"
LEGACY_THRESHOLD_CONFIG_PATH = "ml/artifacts/public_payment_model/threshold_config.json"
MODEL_VERSION = "public_payment_model_v1"


def load_model(model_path=DEFAULT_MODEL_PATH):
	"""Load a persisted scikit-learn model artifact."""

	import joblib

	return joblib.load(model_path)


def load_threshold_config(threshold_config_path=DEFAULT_THRESHOLD_CONFIG_PATH):
	"""Load selected-threshold configuration, falling back to 0.5."""

	path = Path(threshold_config_path)
	if not path.exists():
		legacy_path = Path(LEGACY_THRESHOLD_CONFIG_PATH)
		if legacy_path.exists():
			return json.loads(legacy_path.read_text(encoding="utf-8"))

		return {
			"selected_threshold": 0.5,
			"strategy": "default_0.5_no_threshold_config",
		}

	return json.loads(path.read_text(encoding="utf-8"))


def predict_public_payment_risk(
	company_features,
	model=None,
	model_path=DEFAULT_MODEL_PATH,
	threshold_config=None,
	threshold_config_path=DEFAULT_THRESHOLD_CONFIG_PATH,
	top_n=5,
):
	"""Predict public slow-payer risk for one company/reporting-period feature row."""

	model = model or load_model(model_path)
	threshold_config = threshold_config or load_threshold_config(threshold_config_path)
	selected_threshold = float(threshold_config.get("selected_threshold", 0.5))
	feature_frame = build_feature_frame(company_features)

	probability = float(model.predict_proba(feature_frame)[0][1])
	predicted_label = int(probability >= selected_threshold)
	explanation = get_prediction_explanation(model, feature_frame, top_n=top_n)

	return {
		"probability": round(probability, 6),
		"selected_threshold": selected_threshold,
		"risk_band": assign_prediction_risk_band(probability, selected_threshold),
		"predicted_label": predicted_label,
		"explanation_type": explanation["explanation_type"],
		"top_positive_drivers": explanation["top_positive_drivers"],
		"top_negative_drivers": explanation["top_negative_drivers"],
		"feature_snapshot": feature_frame.iloc[0].to_dict(),
		"model_version": MODEL_VERSION,
		"model_artifact_path": str(model_path),
	}


def build_feature_frame(company_features):
	"""Build a one-row feature DataFrame containing all expected model features."""

	row = {}
	for column in FEATURE_COLUMNS:
		if isinstance(company_features, pd.Series):
			row[column] = company_features.get(column)
		else:
			row[column] = company_features.get(column)

	return pd.DataFrame([row], columns=FEATURE_COLUMNS)


def assign_prediction_risk_band(probability, selected_threshold):
	"""Assign a simple business-facing risk band from model probability."""

	if probability >= selected_threshold:
		return "High"
	if probability >= 0.3:
		return "Medium"
	return "Low"


def get_prediction_explanation(model, feature_frame, top_n=5):
	"""Return the best available explanation for a fitted model pipeline."""

	coefficient_explanation = get_logistic_regression_contributions(model, feature_frame, top_n=top_n)
	if coefficient_explanation["top_positive_drivers"] or coefficient_explanation["top_negative_drivers"]:
		return {
			"explanation_type": "local_linear_contribution",
			**coefficient_explanation,
		}

	importance_explanation = get_tree_feature_importance(model, top_n=top_n)
	if importance_explanation["top_positive_drivers"]:
		return {
			"explanation_type": "global_feature_importance",
			**importance_explanation,
		}

	return {
		"explanation_type": "unavailable",
		"top_positive_drivers": [],
		"top_negative_drivers": [],
	}


def get_logistic_regression_contributions(model, feature_frame, top_n=5):
	"""Return top positive and negative coefficient-based contributions."""

	if "preprocessor" not in model.named_steps or "model" not in model.named_steps:
		return {"top_positive_drivers": [], "top_negative_drivers": []}

	preprocessor = model.named_steps["preprocessor"]
	classifier = model.named_steps["model"]

	if not hasattr(classifier, "coef_"):
		return {"top_positive_drivers": [], "top_negative_drivers": []}

	transformed = preprocessor.transform(feature_frame)
	if hasattr(transformed, "toarray"):
		transformed = transformed.toarray()

	feature_names = preprocessor.get_feature_names_out()
	coefficients = classifier.coef_[0]
	contribution_values = transformed[0] * coefficients

	contributions = []
	for feature_name, coefficient, contribution in zip(
		feature_names,
		coefficients,
		contribution_values,
		strict=False,
	):
		if contribution == 0:
			continue
		contributions.append(
			{
				"feature": str(feature_name),
				"coefficient": round(float(coefficient), 6),
				"contribution": round(float(contribution), 6),
			}
		)

	positive = sorted(
		[item for item in contributions if item["contribution"] > 0],
		key=lambda item: item["contribution"],
		reverse=True,
	)[:top_n]
	negative = sorted(
		[item for item in contributions if item["contribution"] < 0],
		key=lambda item: item["contribution"],
	)[:top_n]

	return {
		"top_positive_drivers": positive,
		"top_negative_drivers": negative,
	}


def get_tree_feature_importance(model, top_n=5):
	"""Return global feature importance for tree/boosting models when available."""

	if "preprocessor" not in model.named_steps or "model" not in model.named_steps:
		return {"top_positive_drivers": [], "top_negative_drivers": []}

	preprocessor = model.named_steps["preprocessor"]
	classifier = model.named_steps["model"]

	if not hasattr(classifier, "feature_importances_"):
		return {"top_positive_drivers": [], "top_negative_drivers": []}

	feature_names = preprocessor.get_feature_names_out()
	importances = classifier.feature_importances_
	drivers = []

	for feature_name, importance in zip(feature_names, importances, strict=False):
		if importance == 0:
			continue
		drivers.append(
			{
				"feature": str(feature_name),
				"importance": round(float(importance), 6),
			}
		)

	return {
		"top_positive_drivers": sorted(drivers, key=lambda item: item["importance"], reverse=True)[:top_n],
		"top_negative_drivers": [],
	}

"""Threshold and calibration utilities for public payment risk models."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


DEFAULT_THRESHOLDS = [round(value / 100, 2) for value in range(20, 81, 5)]


def evaluate_probability_thresholds(y_true, probabilities, thresholds=None):
	"""Return precision/recall/F1/confusion metrics for probability thresholds."""

	from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

	thresholds = thresholds or DEFAULT_THRESHOLDS
	rows = []

	for threshold in thresholds:
		predictions = [int(probability >= threshold) for probability in probabilities]
		true_negative, false_positive, false_negative, true_positive = confusion_matrix(
			y_true,
			predictions,
			labels=[0, 1],
		).ravel()

		rows.append(
			{
				"threshold": threshold,
				"precision": round(float(precision_score(y_true, predictions, zero_division=0)), 4),
				"recall": round(float(recall_score(y_true, predictions, zero_division=0)), 4),
				"f1": round(float(f1_score(y_true, predictions, zero_division=0)), 4),
				"true_positive": int(true_positive),
				"false_positive": int(false_positive),
				"true_negative": int(true_negative),
				"false_negative": int(false_negative),
			}
		)

	return pd.DataFrame(rows)


def select_recommended_threshold(threshold_report, recall_floor=0.8):
	"""Select a threshold by max F1 among rows meeting a recall floor.

	If no threshold satisfies the recall floor, the highest-F1 threshold overall
	is selected. Ties prefer higher recall, then higher threshold to reduce noise.
	"""

	if threshold_report.empty:
		raise ValueError("Cannot select a threshold from an empty threshold report.")

	candidates = threshold_report[threshold_report["recall"] >= recall_floor]
	strategy = f"max_f1_with_recall_floor_{recall_floor}"

	if candidates.empty:
		candidates = threshold_report
		strategy = "max_f1_no_recall_floor_match"

	selected = candidates.sort_values(
		["f1", "recall", "threshold"],
		ascending=[False, False, False],
	).iloc[0]

	return {
		"selected_threshold": float(selected["threshold"]),
		"strategy": strategy,
		"recall_floor": recall_floor,
		"precision": float(selected["precision"]),
		"recall": float(selected["recall"]),
		"f1": float(selected["f1"]),
		"true_positive": int(selected["true_positive"]),
		"false_positive": int(selected["false_positive"]),
		"true_negative": int(selected["true_negative"]),
		"false_negative": int(selected["false_negative"]),
	}


def calculate_calibration_metrics(y_true, probabilities, n_bins=10):
	"""Return Brier score and calibration-curve bin data."""

	from sklearn.calibration import calibration_curve
	from sklearn.metrics import brier_score_loss

	observed_positive_rate, mean_predicted_probability = calibration_curve(
		y_true,
		probabilities,
		n_bins=n_bins,
		strategy="uniform",
	)

	bins = []
	for mean_probability, observed_rate in zip(mean_predicted_probability, observed_positive_rate, strict=False):
		bins.append(
			{
				"mean_predicted_probability": round(float(mean_probability), 6),
				"observed_positive_rate": round(float(observed_rate), 6),
			}
		)

	return {
		"brier_score": round(float(brier_score_loss(y_true, probabilities)), 6),
		"n_bins": n_bins,
		"calibration_bins": bins,
		"calibrated_model_created": False,
		"calibration_note": "Evaluation only. CalibratedClassifierCV can be added later if calibration drift is material.",
	}


def export_threshold_report(threshold_report, output_path):
	"""Write threshold report CSV."""

	path = Path(output_path)
	path.parent.mkdir(parents=True, exist_ok=True)
	threshold_report.to_csv(path, index=False)
	return path


def export_json(data, output_path):
	"""Write JSON artifact."""

	path = Path(output_path)
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, indent=2), encoding="utf-8")
	return path

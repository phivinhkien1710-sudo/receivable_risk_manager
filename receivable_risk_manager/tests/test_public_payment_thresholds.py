import unittest

import pandas as pd

from receivable_risk_manager.ml.public_payment_thresholds import (
	calculate_calibration_metrics,
	evaluate_probability_thresholds,
	select_recommended_threshold,
)


class TestPublicPaymentThresholds(unittest.TestCase):
	def test_threshold_metrics_include_confusion_counts(self):
		y_true = pd.Series([0, 0, 1, 1])
		probabilities = [0.1, 0.4, 0.7, 0.9]

		report = evaluate_probability_thresholds(y_true, probabilities, thresholds=[0.5])
		row = report.iloc[0].to_dict()

		self.assertEqual(row["threshold"], 0.5)
		self.assertEqual(row["true_positive"], 2)
		self.assertEqual(row["false_positive"], 0)
		self.assertEqual(row["true_negative"], 2)
		self.assertEqual(row["false_negative"], 0)
		self.assertEqual(row["precision"], 1.0)
		self.assertEqual(row["recall"], 1.0)

	def test_select_threshold_prefers_f1_with_recall_floor(self):
		report = pd.DataFrame(
			[
				{"threshold": 0.3, "precision": 0.4, "recall": 0.9, "f1": 0.55, "true_positive": 9, "false_positive": 6, "true_negative": 4, "false_negative": 1},
				{"threshold": 0.5, "precision": 0.7, "recall": 0.8, "f1": 0.75, "true_positive": 8, "false_positive": 3, "true_negative": 7, "false_negative": 2},
				{"threshold": 0.7, "precision": 0.9, "recall": 0.5, "f1": 0.64, "true_positive": 5, "false_positive": 1, "true_negative": 9, "false_negative": 5},
			]
		)

		selected = select_recommended_threshold(report, recall_floor=0.8)

		self.assertEqual(selected["selected_threshold"], 0.5)
		self.assertEqual(selected["strategy"], "max_f1_with_recall_floor_0.8")

	def test_select_threshold_falls_back_when_recall_floor_not_met(self):
		report = pd.DataFrame(
			[
				{"threshold": 0.5, "precision": 0.7, "recall": 0.5, "f1": 0.58, "true_positive": 5, "false_positive": 2, "true_negative": 8, "false_negative": 5},
				{"threshold": 0.6, "precision": 0.8, "recall": 0.4, "f1": 0.53, "true_positive": 4, "false_positive": 1, "true_negative": 9, "false_negative": 6},
			]
		)

		selected = select_recommended_threshold(report, recall_floor=0.8)

		self.assertEqual(selected["selected_threshold"], 0.5)
		self.assertEqual(selected["strategy"], "max_f1_no_recall_floor_match")

	def test_calibration_metrics_schema(self):
		metrics = calculate_calibration_metrics(
			pd.Series([0, 0, 1, 1]),
			[0.1, 0.2, 0.8, 0.9],
			n_bins=2,
		)

		self.assertIn("brier_score", metrics)
		self.assertIn("calibration_bins", metrics)
		self.assertGreaterEqual(len(metrics["calibration_bins"]), 1)


if __name__ == "__main__":
	unittest.main()

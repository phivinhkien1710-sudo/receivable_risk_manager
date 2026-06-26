"""Broad model benchmark for GOV.UK public payment slow-payer prediction.

This module is intentionally offline-only. It benchmarks viable scikit-learn
models using the same ML-ready dataset, feature columns, target, and
company-based train/test split.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
import time
from pathlib import Path

import pandas as pd

from receivable_risk_manager.ml.public_payment_thresholds import (
	calculate_calibration_metrics,
	evaluate_probability_thresholds,
	export_json,
	export_threshold_report,
	select_recommended_threshold,
)
from receivable_risk_manager.ml.train_public_payment_model import (
	FEATURE_COLUMNS,
	build_preprocessor,
	extract_feature_importance,
	get_positive_class_probabilities,
	load_ml_ready_data,
	prepare_training_data,
	split_train_test_by_company,
)


BENCHMARK_THRESHOLDS = [round(value / 100, 2) for value in range(20, 91, 5)]
REQUIRED_RESULT_FIELDS = [
	"model_name",
	"status",
	"accuracy",
	"precision",
	"recall",
	"f1",
	"roc_auc",
	"pr_auc",
	"brier_score",
	"true_positive",
	"false_positive",
	"true_negative",
	"false_negative",
	"selected_threshold",
	"threshold_strategy",
	"training_time_seconds",
	"inference_time_seconds",
	"model_size_bytes",
	"skip_reason",
]


def build_model_registry(random_state=42):
	"""Return benchmark model registry with skipped-model reasons where useful."""

	from sklearn.dummy import DummyClassifier
	from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
	from sklearn.linear_model import LogisticRegression, RidgeClassifier, SGDClassifier
	from sklearn.svm import LinearSVC
	from sklearn.tree import DecisionTreeClassifier

	registry = {
		"dummy_majority": {
			"estimator": DummyClassifier(strategy="most_frequent"),
			"supports_sparse_onehot": True,
			"notes": "Majority-class baseline.",
		},
		"dummy_stratified": {
			"estimator": DummyClassifier(strategy="stratified", random_state=random_state),
			"supports_sparse_onehot": True,
			"notes": "Random stratified baseline.",
		},
		"logistic_regression_balanced": {
			"estimator": LogisticRegression(max_iter=1000, class_weight="balanced", random_state=random_state),
			"supports_sparse_onehot": True,
			"notes": "Current explainable baseline to beat.",
		},
		"logistic_regression_unweighted": {
			"estimator": LogisticRegression(max_iter=1000, random_state=random_state),
			"supports_sparse_onehot": True,
			"notes": "Unweighted logistic comparison.",
		},
		"sgd_log_loss_balanced": {
			"estimator": SGDClassifier(
				loss="log_loss",
				class_weight="balanced",
				max_iter=1000,
				tol=1e-3,
				random_state=random_state,
			),
			"supports_sparse_onehot": True,
			"notes": "Fast linear probabilistic classifier.",
		},
		"ridge_classifier_balanced": {
			"estimator": RidgeClassifier(class_weight="balanced", random_state=random_state),
			"supports_sparse_onehot": True,
			"notes": "Linear classifier with decision scores but no probabilities.",
		},
		"decision_tree_balanced": {
			"estimator": DecisionTreeClassifier(
				max_depth=12,
				min_samples_leaf=50,
				class_weight="balanced",
				random_state=random_state,
			),
			"supports_sparse_onehot": True,
			"notes": "Simple tree baseline with regularization.",
		},
		"random_forest_balanced": {
			"estimator": RandomForestClassifier(
				n_estimators=200,
				min_samples_leaf=10,
				class_weight="balanced",
				random_state=random_state,
				n_jobs=-1,
			),
			"supports_sparse_onehot": True,
			"notes": "Tree ensemble baseline.",
		},
		"extra_trees_balanced": {
			"estimator": ExtraTreesClassifier(
				n_estimators=200,
				min_samples_leaf=10,
				class_weight="balanced",
				random_state=random_state,
				n_jobs=-1,
			),
			"supports_sparse_onehot": True,
			"notes": "Randomized tree ensemble baseline.",
		},
		"linear_svc_balanced": {
			"estimator": LinearSVC(class_weight="balanced", random_state=random_state, max_iter=5000),
			"supports_sparse_onehot": True,
			"notes": "Linear SVM with decision scores; no probability threshold tuning.",
		},
		"gaussian_nb": {
			"skip_reason": "Skipped: GaussianNB requires dense arrays; dense one-hot is not a good default for the current mixed numeric/categorical pipeline.",
		},
		"gradient_boosting": {
			"skip_reason": "Skipped: GradientBoostingClassifier is dense-only and slower than the selected sparse-friendly baselines for this dataset.",
		},
		"hist_gradient_boosting": {
			"skip_reason": "Skipped: HistGradientBoostingClassifier does not support sparse one-hot input without a separate preprocessing path.",
		},
		"adaboost": {
			"skip_reason": "Skipped: AdaBoost is not a good runtime/accuracy tradeoff compared with the selected tabular baselines.",
		},
		"kernel_svc": {
			"skip_reason": "Skipped: full kernel SVC is too slow for 100k rows and sparse one-hot categorical features.",
		},
		"knn": {
			"skip_reason": "Skipped: KNN inference is too slow for this 100k-row sparse tabular benchmark.",
		},
	}

	registry.update(build_optional_model_registry(random_state=random_state))

	return registry


def build_optional_model_registry(random_state=42):
	"""Return optional external model configs when dependencies are installed."""

	optional_registry = {}

	if importlib.util.find_spec("xgboost"):
		try:
			from xgboost import XGBClassifier

			optional_registry["xgboost"] = {
				"estimator": XGBClassifier(
					n_estimators=200,
					max_depth=4,
					learning_rate=0.05,
					subsample=0.9,
					colsample_bytree=0.9,
					objective="binary:logistic",
					eval_metric="logloss",
					tree_method="hist",
					scale_pos_weight=10.75,
					random_state=random_state,
					n_jobs=-1,
				),
				"supports_sparse_onehot": True,
				"notes": "Optional external gradient boosting model with sparse one-hot support.",
			}
		except Exception as exc:
			optional_registry["xgboost"] = {
				"skip_reason": format_optional_import_error("xgboost", exc),
			}
	else:
		optional_registry["xgboost"] = {
			"skip_reason": "Skipped: optional dependency xgboost is not installed.",
		}

	if importlib.util.find_spec("lightgbm"):
		try:
			from lightgbm import LGBMClassifier

			optional_registry["lightgbm"] = {
				"estimator": LGBMClassifier(
					n_estimators=200,
					max_depth=-1,
					num_leaves=31,
					learning_rate=0.05,
					subsample=0.9,
					colsample_bytree=0.9,
					class_weight="balanced",
					random_state=random_state,
					n_jobs=-1,
					verbosity=-1,
				),
				"supports_sparse_onehot": True,
				"notes": "Optional external gradient boosting model with sparse one-hot support.",
			}
		except Exception as exc:
			optional_registry["lightgbm"] = {
				"skip_reason": format_optional_import_error("lightgbm", exc),
			}
	else:
		optional_registry["lightgbm"] = {
			"skip_reason": "Skipped: optional dependency lightgbm is not installed.",
		}

	if importlib.util.find_spec("catboost"):
		try:
			from catboost import CatBoostClassifier

			optional_registry["catboost"] = {
				"estimator": CatBoostClassifier(
					iterations=200,
					depth=6,
					learning_rate=0.05,
					loss_function="Logloss",
					eval_metric="AUC",
					auto_class_weights="Balanced",
					random_seed=random_state,
					verbose=False,
					allow_writing_files=False,
				),
				"supports_sparse_onehot": True,
				"notes": "Optional external gradient boosting model. Uses one-hot output rather than CatBoost native categorical handling.",
			}
		except Exception as exc:
			optional_registry["catboost"] = {
				"skip_reason": format_optional_import_error("catboost", exc),
			}
	else:
		optional_registry["catboost"] = {
			"skip_reason": "Skipped: optional dependency catboost is not installed.",
		}

	return optional_registry


def format_optional_import_error(package_name, exc):
	"""Return a concise skip reason for optional ML package import failures."""

	message = str(exc)
	if "libomp" in message:
		return (
			f"Skipped: {package_name} is installed but requires the OpenMP runtime "
			"`libomp` on this Mac. Install with `brew install libomp` to enable it."
		)

	return f"Skipped: {package_name} is installed but could not be imported ({exc.__class__.__name__})."


def build_pipeline(estimator):
	"""Build a benchmark pipeline with the shared preprocessing rules."""

	from sklearn.pipeline import Pipeline

	return Pipeline(
		steps=[
			("preprocessor", build_preprocessor()),
			("model", estimator),
		]
	)


def run_model_benchmark(
	input_path="ml/data/processed/public_payment_ml_ready.csv",
	output_dir="ml/artifacts/public_payment_model",
	processed_dir="ml/data/processed",
	test_size=0.2,
	random_state=42,
	recall_floor=0.8,
	model_names=None,
):
	"""Run the Stage A broad benchmark and export comparison artifacts."""

	df = load_ml_ready_data(input_path)
	x, y, groups = prepare_training_data(df)
	split = split_train_test_by_company(x, y, groups, test_size=test_size, random_state=random_state)
	registry = build_model_registry(random_state=random_state)
	results = []
	trained_models = {}
	threshold_reports = {}

	for model_name, config in registry.items():
		if model_names and model_name not in model_names:
			continue
		if config.get("skip_reason"):
			results.append(build_skipped_result(model_name, config["skip_reason"]))
			continue

		model_result, model, threshold_report = train_and_evaluate_benchmark_model(
			model_name,
			config,
			split["x_train"],
			split["y_train"],
			split["x_test"],
			split["y_test"],
			recall_floor=recall_floor,
		)
		results.append(model_result)
		trained_models[model_name] = model
		if threshold_report is not None:
			threshold_reports[model_name] = threshold_report

	result_df = pd.DataFrame(results)
	for field in REQUIRED_RESULT_FIELDS:
		if field not in result_df.columns:
			result_df[field] = None
	result_df = result_df[REQUIRED_RESULT_FIELDS]

	selection = select_final_model(result_df)
	artifact_paths = export_benchmark_artifacts(
		result_df,
		threshold_reports,
		trained_models,
		selection,
		output_dir=output_dir,
		processed_dir=processed_dir,
	)

	return {
		"rows_used": int(len(y)),
		"train_companies": int(split["train_groups"].nunique()),
		"test_companies": int(split["test_groups"].nunique()),
		"group_overlap": int(len(set(split["train_groups"]).intersection(set(split["test_groups"])))),
		"models_benchmarked": int((result_df["status"] == "trained").sum()),
		"models_skipped": int((result_df["status"] == "skipped").sum()),
		"selected_model": selection,
		"artifact_paths": artifact_paths,
	}


def train_and_evaluate_benchmark_model(model_name, config, x_train, y_train, x_test, y_test, recall_floor=0.8):
	"""Train one benchmark model and return metrics plus optional threshold report."""

	model = build_pipeline(config["estimator"])

	start = time.perf_counter()
	model.fit(x_train, y_train)
	training_time = time.perf_counter() - start

	start = time.perf_counter()
	default_predictions = model.predict(x_test)
	probabilities = get_probability_scores(model, x_test)
	decision_scores = None if probabilities is not None else get_decision_scores(model, x_test)
	inference_time = time.perf_counter() - start

	score_values = probabilities if probabilities is not None else decision_scores
	metrics = calculate_default_metrics(y_test, default_predictions, score_values, probabilities)
	threshold_report = None
	threshold_config = None

	if probabilities is not None:
		threshold_report = evaluate_probability_thresholds(
			y_test,
			probabilities,
			thresholds=BENCHMARK_THRESHOLDS,
		)
		threshold_config = select_recommended_threshold(threshold_report, recall_floor=recall_floor)
		metrics.update(
			{
				"precision": threshold_config["precision"],
				"recall": threshold_config["recall"],
				"f1": threshold_config["f1"],
				"true_positive": threshold_config["true_positive"],
				"false_positive": threshold_config["false_positive"],
				"true_negative": threshold_config["true_negative"],
				"false_negative": threshold_config["false_negative"],
				"selected_threshold": threshold_config["selected_threshold"],
				"threshold_strategy": threshold_config["strategy"],
			}
		)
	else:
		metrics["selected_threshold"] = None
		metrics["threshold_strategy"] = "not_available_no_predict_proba"

	metrics.update(
		{
			"model_name": model_name,
			"status": "trained",
			"training_time_seconds": round(float(training_time), 4),
			"inference_time_seconds": round(float(inference_time), 4),
			"model_size_bytes": estimate_model_size_bytes(model),
			"skip_reason": "",
		}
	)

	return metrics, model, threshold_report


def calculate_default_metrics(y_true, predictions, score_values=None, probabilities=None):
	"""Calculate default classification metrics."""

	from sklearn.metrics import (
		accuracy_score,
		average_precision_score,
		brier_score_loss,
		confusion_matrix,
		f1_score,
		precision_score,
		recall_score,
		roc_auc_score,
	)

	true_negative, false_positive, false_negative, true_positive = confusion_matrix(
		y_true,
		predictions,
		labels=[0, 1],
	).ravel()

	metrics = {
		"accuracy": round(float(accuracy_score(y_true, predictions)), 4),
		"precision": round(float(precision_score(y_true, predictions, zero_division=0)), 4),
		"recall": round(float(recall_score(y_true, predictions, zero_division=0)), 4),
		"f1": round(float(f1_score(y_true, predictions, zero_division=0)), 4),
		"true_positive": int(true_positive),
		"false_positive": int(false_positive),
		"true_negative": int(true_negative),
		"false_negative": int(false_negative),
		"roc_auc": None,
		"pr_auc": None,
		"brier_score": None,
	}

	if score_values is not None:
		metrics["roc_auc"] = round(float(roc_auc_score(y_true, score_values)), 4)
		metrics["pr_auc"] = round(float(average_precision_score(y_true, score_values)), 4)

	if probabilities is not None:
		metrics["brier_score"] = round(float(brier_score_loss(y_true, probabilities)), 6)

	return metrics


def get_probability_scores(model, x_test):
	"""Return positive-class probabilities when supported."""

	if not hasattr(model, "predict_proba"):
		return None

	try:
		probabilities = model.predict_proba(x_test)
	except AttributeError:
		return None

	if probabilities.shape[1] < 2:
		return None

	return probabilities[:, 1]


def get_decision_scores(model, x_test):
	"""Return decision scores when probabilities are unavailable."""

	if not hasattr(model, "decision_function"):
		return None

	try:
		return model.decision_function(x_test)
	except AttributeError:
		return None


def build_skipped_result(model_name, reason):
	"""Return a standardized skipped-result row."""

	return {
		"model_name": model_name,
		"status": "skipped",
		"skip_reason": reason,
	}


def estimate_model_size_bytes(model):
	"""Estimate serialized model size without keeping temporary files."""

	import joblib

	with tempfile.NamedTemporaryFile(suffix=".joblib") as temp_file:
		joblib.dump(model, temp_file.name)
		return int(Path(temp_file.name).stat().st_size)


def select_final_model(result_df, baseline_model="logistic_regression_balanced", recall_floor=0.8, min_f1_improvement=0.02):
	"""Select final model while keeping Logistic Regression unless improvement is meaningful."""

	trained = result_df[result_df["status"] == "trained"].copy()
	if trained.empty:
		raise ValueError("No trained models available for final selection.")

	eligible = trained[trained["recall"].fillna(0) >= recall_floor]
	if eligible.empty:
		eligible = trained
		selection_pool = "no_model_met_recall_floor"
	else:
		selection_pool = f"recall_at_least_{recall_floor}"

	winner = eligible.sort_values(
		["f1", "precision", "pr_auc"],
		ascending=[False, False, False],
	).iloc[0]

	baseline_rows = trained[trained["model_name"] == baseline_model]
	if baseline_rows.empty:
		final = winner
		reason = "baseline_missing_selected_best_available_model"
	else:
		baseline = baseline_rows.iloc[0]
		if winner["model_name"] == baseline_model:
			final = winner
			reason = "baseline_logistic_regression_won_selection_rule"
		elif float(winner.get("f1") or 0) >= float(baseline.get("f1") or 0) + min_f1_improvement:
			final = winner
			reason = "replacement_model_met_minimum_f1_improvement"
		else:
			final = baseline
			reason = "kept_logistic_regression_due_to_insufficient_improvement"

	return {
		"selected_model": final["model_name"],
		"selection_reason": reason,
		"selection_pool": selection_pool,
		"recall_floor": recall_floor,
		"min_f1_improvement_required": min_f1_improvement,
		"precision": none_or_float(final.get("precision")),
		"recall": none_or_float(final.get("recall")),
		"f1": none_or_float(final.get("f1")),
		"roc_auc": none_or_float(final.get("roc_auc")),
		"pr_auc": none_or_float(final.get("pr_auc")),
		"brier_score": none_or_float(final.get("brier_score")),
		"selected_threshold": none_or_float(final.get("selected_threshold")),
	}


def none_or_float(value):
	if pd.isna(value):
		return None
	return float(value)


def export_benchmark_artifacts(result_df, threshold_reports, trained_models, selection, output_dir, processed_dir):
	"""Write benchmark results and final selected-model artifacts."""

	import joblib

	output_path = Path(output_dir)
	processed_path = Path(processed_dir)
	threshold_dir = processed_path / "model_threshold_reports"
	output_path.mkdir(parents=True, exist_ok=True)
	processed_path.mkdir(parents=True, exist_ok=True)
	threshold_dir.mkdir(parents=True, exist_ok=True)

	csv_path = processed_path / "model_benchmark_results.csv"
	json_path = processed_path / "model_benchmark_results.json"
	comparison_path = output_path / "model_comparison.md"
	best_model_path = output_path / "best_model.joblib"
	model_metrics_path = output_path / "model_metrics.json"
	training_columns_path = output_path / "training_columns.json"
	feature_importance_path = output_path / "feature_importance.csv"
	selected_threshold_path = output_path / "selected_threshold.json"
	calibration_metrics_path = output_path / "calibration_metrics.json"

	result_df.to_csv(csv_path, index=False)
	json_path.write_text(result_df.to_json(orient="records", indent=2), encoding="utf-8")

	for model_name, threshold_report in threshold_reports.items():
		export_threshold_report(threshold_report, threshold_dir / f"{model_name}.csv")

	selected_model_name = selection["selected_model"]
	selected_model = trained_models[selected_model_name]
	joblib.dump(selected_model, best_model_path)
	training_columns_path.write_text(json.dumps(FEATURE_COLUMNS, indent=2), encoding="utf-8")

	final_metrics = {
		"final_selection": selection,
		"benchmark_results": json.loads(result_df.to_json(orient="records")),
	}
	export_json(final_metrics, model_metrics_path)

	selected_threshold = {
		"selected_model": selected_model_name,
		"selected_threshold": selection.get("selected_threshold"),
		"selection_reason": selection.get("selection_reason"),
	}
	export_json(selected_threshold, selected_threshold_path)

	selected_rows = result_df[result_df["model_name"] == selected_model_name]
	if not selected_rows.empty and selected_rows.iloc[0].get("brier_score") is not None:
		# Calibration metrics are recomputed in the focused trainer; benchmark stores summary only.
		export_json(
			{
				"selected_model": selected_model_name,
				"brier_score": none_or_float(selected_rows.iloc[0].get("brier_score")),
				"calibration_note": "Full calibration curve is produced by train_public_payment_model.py for the final model.",
			},
			calibration_metrics_path,
		)

	try:
		extract_feature_importance(selected_model, selected_model_name).to_csv(feature_importance_path, index=False)
	except Exception:
		pd.DataFrame().to_csv(feature_importance_path, index=False)

	comparison_path.write_text(build_model_comparison_markdown(result_df, selection), encoding="utf-8")

	return {
		"benchmark_csv_path": str(csv_path),
		"benchmark_json_path": str(json_path),
		"threshold_reports_dir": str(threshold_dir),
		"model_comparison_path": str(comparison_path),
		"best_model_path": str(best_model_path),
		"model_metrics_path": str(model_metrics_path),
		"training_columns_path": str(training_columns_path),
		"feature_importance_path": str(feature_importance_path),
		"selected_threshold_path": str(selected_threshold_path),
		"calibration_metrics_path": str(calibration_metrics_path),
	}


def build_model_comparison_markdown(result_df, selection):
	"""Build a concise markdown model comparison report."""

	trained = result_df[result_df["status"] == "trained"].copy()
	trained = trained.sort_values(["f1", "precision", "pr_auc"], ascending=[False, False, False])
	skipped = result_df[result_df["status"] == "skipped"].copy()

	lines = [
		"# Public Payment Model Benchmark",
		"",
		"Stage A broad benchmark using the same GOV.UK ML-ready dataset, feature columns, target, and company-based split.",
		"",
		"## Final Selection",
		"",
		f"- Selected model: `{selection['selected_model']}`",
		f"- Reason: {selection['selection_reason']}",
		f"- Recall floor: {selection['recall_floor']}",
		f"- Minimum F1 improvement required to replace Logistic Regression: {selection['min_f1_improvement_required']}",
		"",
		"## Trained Models",
		"",
		"| Model | Precision | Recall | F1 | ROC AUC | PR AUC | Brier | Threshold | Train sec | Infer sec |",
		"| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
	]

	for _, row in trained.iterrows():
		lines.append(
			"| {model} | {precision} | {recall} | {f1} | {roc_auc} | {pr_auc} | {brier} | {threshold} | {train_time} | {infer_time} |".format(
				model=row["model_name"],
				precision=format_metric(row.get("precision")),
				recall=format_metric(row.get("recall")),
				f1=format_metric(row.get("f1")),
				roc_auc=format_metric(row.get("roc_auc")),
				pr_auc=format_metric(row.get("pr_auc")),
				brier=format_metric(row.get("brier_score")),
				threshold=format_metric(row.get("selected_threshold")),
				train_time=format_metric(row.get("training_time_seconds")),
				infer_time=format_metric(row.get("inference_time_seconds")),
			)
		)

	lines.extend(["", "## Skipped Models", ""])
	for _, row in skipped.iterrows():
		lines.append(f"- `{row['model_name']}`: {row['skip_reason']}")

	lines.extend(
		[
			"",
			"## Notes",
			"",
			"- Logistic Regression is the explainable baseline; a more complex model is selected only if it improves F1 materially while preserving recall >= 0.80.",
			"- Dense-only or slow models are skipped unless they offer a clear accuracy or deployment tradeoff.",
			"- This is a company/reporting-period public payment-risk benchmark, not invoice-level default prediction.",
		]
	)

	return "\n".join(lines) + "\n"


def format_metric(value):
	if value is None or pd.isna(value):
		return ""
	if isinstance(value, float):
		return f"{value:.4f}"
	return str(value)


def main():
	parser = argparse.ArgumentParser(description="Benchmark public payment slow-payer models.")
	parser.add_argument("--input", default="ml/data/processed/public_payment_ml_ready.csv")
	parser.add_argument("--output-dir", default="ml/artifacts/public_payment_model")
	parser.add_argument("--processed-dir", default="ml/data/processed")
	parser.add_argument("--test-size", type=float, default=0.2)
	parser.add_argument("--random-state", type=int, default=42)
	parser.add_argument("--recall-floor", type=float, default=0.8)
	parser.add_argument(
		"--models",
		default="",
		help="Optional comma-separated model names to run for a quick subset.",
	)

	args = parser.parse_args()
	model_names = [name.strip() for name in args.models.split(",") if name.strip()] or None
	summary = run_model_benchmark(
		input_path=args.input,
		output_dir=args.output_dir,
		processed_dir=args.processed_dir,
		test_size=args.test_size,
		random_state=args.random_state,
		recall_floor=args.recall_floor,
		model_names=model_names,
	)
	print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
	main()

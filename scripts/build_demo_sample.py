#!/usr/bin/env python3
"""Builds a small, open-invoices-only sample CSV for demo_reset.sh.

Not run automatically -- local_data/demo_500_open.csv is gitignored the same
way local_data/dataset_clean.csv is, so this is what regenerates it.

Why this exists rather than just `head -500 dataset_clean.csv`: the source
file is ordered such that its earliest rows are old, already-closed invoices
(is_open=0) -- a naive head/tail/stride sample produced a demo with zero open
invoices and an empty dashboard, found by actually running it. This filters
to is_open=1 first, then weights toward the most-overdue rows so a
High-risk-scored invoice (the case that makes AI review's judgment visible at
all) is reasonably likely to appear, rather than leaving it to chance.

Usage:
  python3 scripts/build_demo_sample.py [--size 500] [--out local_data/demo_500_open.csv]
"""

import argparse
import csv
from datetime import date
from pathlib import Path


def overdue_proxy(row):
	"""Crude ranking signal from the raw CSV alone (posting_date vs
	due_date) -- not the same computation invoice_risk.py uses (that needs
	an analysis_date and customer risk, neither available pre-import), just
	a proxy for "this row is more likely to score High" ordering."""
	try:
		due = date.fromisoformat(row["due_date"])
		posting = date.fromisoformat(row["posting_date"])
		return (posting - due).days
	except Exception:
		return 0


def build_sample(src_path, out_path, size):
	with open(src_path, newline="", encoding="utf-8") as f:
		reader = csv.DictReader(f)
		fieldnames = reader.fieldnames
		open_rows = [row for row in reader if row.get("is_open") == "1"]

	if not open_rows:
		raise SystemExit(f"No is_open=1 rows found in {src_path}")

	ranked = sorted(open_rows, key=overdue_proxy, reverse=True)
	skewed_high = ranked[: size // 3]

	remainder_pool = open_rows[len(open_rows) // 2 :: 7]
	seen = {r.get("invoice_id") or r.get("doc_id") for r in skewed_high}
	spread = [r for r in remainder_pool if (r.get("invoice_id") or r.get("doc_id")) not in seen]

	sample = (skewed_high + spread)[:size]

	Path(out_path).parent.mkdir(parents=True, exist_ok=True)
	with open(out_path, "w", newline="", encoding="utf-8") as f:
		writer = csv.DictWriter(f, fieldnames=fieldnames)
		writer.writeheader()
		writer.writerows(sample)

	print(f"wrote {len(sample)} rows to {out_path}")


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("--src", default="local_data/dataset_clean.csv")
	parser.add_argument("--out", default="local_data/demo_500_open.csv")
	parser.add_argument("--size", type=int, default=500)
	args = parser.parse_args()

	repo_root = Path(__file__).resolve().parent.parent
	build_sample(repo_root / args.src, repo_root / args.out, args.size)

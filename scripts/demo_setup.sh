#!/usr/bin/env bash
#
# One-command demo setup for Receivables Risk Manager.
#
# Installs the app on a site (if needed), imports the local dataset, and runs
# the full risk recalculation pipeline, so a reviewer can go from a fresh
# bench to a screenshot-ready dashboard without following the manual README
# steps one by one.
#
# Usage:
#   ./scripts/demo_setup.sh <site-name> [csv-path] [row-limit]
#
# Examples:
#   ./scripts/demo_setup.sh staging.local
#   ./scripts/demo_setup.sh staging.local local_data/dataset_clean.csv 2000

set -euo pipefail

SITE="${1:?Usage: $0 <site-name> [csv-path] [row-limit]}"
CSV_PATH="${2:-local_data/dataset_clean.csv}"
ROW_LIMIT="${3:-2000}"

BENCH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ABS_CSV_PATH="$BENCH_ROOT/apps/receivable_risk_manager/$CSV_PATH"
cd "$BENCH_ROOT"

# NOTE: the `bench` CLI chdirs into sites/ before running any command, so
# relative paths (as used elsewhere in this project's README) resolve from
# there, not from the bench root. Always pass an absolute csv_path to
# `bench execute` to avoid a confusing "CSV file not found" failure.
if [ ! -f "$ABS_CSV_PATH" ]; then
	echo "CSV file not found: $ABS_CSV_PATH"
	echo "Place a cleaned receivables CSV there before running this script."
	exit 1
fi

echo "== Installing app on $SITE (skips if already installed) =="
bench --site "$SITE" install-app receivable_risk_manager || true

echo "== Migrating $SITE =="
if ! bench --site "$SITE" migrate; then
	echo "WARNING: 'bench migrate' failed. This is commonly an unrelated"
	echo "ERPNext/Frappe patch-history issue on the bench itself, not this app."
	echo "Continuing, since the receivables_risk tables may already be in place."
	echo "If the import step below fails with a schema error, fix the bench's"
	echo "migrate state first (bench --site $SITE migrate for the full traceback)."
fi

echo "== Importing up to $ROW_LIMIT rows from $CSV_PATH =="
bench --site "$SITE" execute receivable_risk_manager.imports.invoice_imports.import_dataset \
	--kwargs "{'csv_path': '$ABS_CSV_PATH', 'limit': $ROW_LIMIT}"

echo "== Running full risk recalculation pipeline =="
bench --site "$SITE" execute receivable_risk_manager.tasks.run_full_recalculation

echo "== Clearing cache =="
bench --site "$SITE" clear-cache

echo
echo "Done. Open http://$SITE:8000 and go to:"
echo "  - Receivables Risk Dashboard"
echo "  - Customer Risk Overview"
echo "  - Invoice Collection Priority"
echo "  - Collection Action Queue"

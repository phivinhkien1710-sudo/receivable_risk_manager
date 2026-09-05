#!/usr/bin/env bash
#
# Resets a site to a small, batch-tracked demo dataset: wipes all existing
# receivables data, imports a CSV through the real Receivables Import Job
# path (not the raw import_dataset() shortcut demo_setup.sh uses), and runs
# the full recalculation pipeline.
#
# Unlike demo_setup.sh, this goes through Receivables Import Job so
# Receivables Batch Member rows get recorded and the completed job's Batch
# Workflow menu (Run AI Review, Review Proposals, ...) has something to
# attach to -- demo_setup.sh's direct import_dataset() call bypasses all of
# that, which defeats the point of demoing the batch-scoped workflow.
#
# Usage:
#   ./scripts/demo_reset.sh <site-name> [csv-path] [as-of-date]
#
# Example:
#   ./scripts/demo_reset.sh staging.local local_data/demo_500_open.csv 2020-05-31

set -euo pipefail

SITE="${1:?Usage: $0 <site-name> [csv-path] [as-of-date]}"
CSV_PATH="${2:-local_data/demo_500_open.csv}"
AS_OF_DATE="${3:-2020-05-31}"

BENCH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ABS_CSV_PATH="$BENCH_ROOT/apps/receivable_risk_manager/$CSV_PATH"
cd "$BENCH_ROOT"

# bench chdirs into sites/ before running any command -- an absolute path is
# not optional here. Hit this for real building this script: a relative path
# failed with FileNotFoundError, which cascaded into an unrelated-looking
# MandatoryError on the Import Job insert three steps later.
if [ ! -f "$ABS_CSV_PATH" ]; then
	echo "CSV file not found: $ABS_CSV_PATH"
	exit 1
fi

bench --site "$SITE" execute receivable_risk_manager.services.demo_reset.reset_and_import \
	--kwargs "{'csv_path': '$ABS_CSV_PATH', 'as_of_date': '$AS_OF_DATE'}"

echo
echo "Done. Open the completed Receivables Import Job in Desk and use its"
echo "Batch Workflow menu to Run AI Review against this batch."

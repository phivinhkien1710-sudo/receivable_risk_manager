#!/usr/bin/env bash
# One-command installer for Receivables Risk Manager.
#
# Wraps Frappe's own official Docker installer (easy-install.py) so a
# non-technical person only has to run this one script instead of the
# multi-step manual process in README.md's "Installing from scratch"
# section (which this script follows exactly — see that section if you
# want to understand what each step below actually does).
#
# This installs the APP ONLY, with no data. If you were given a data
# backup separately (through a private handoff, never from this public
# repo — it would contain real company/contact information), run
# restore-data.sh afterwards.
#
# Usage:
#   ./install.sh
#
# Override any default with an environment variable, e.g.:
#   RRM_SITENAME=my-outreach.local RRM_HTTP_PORT=8090 ./install.sh

set -euo pipefail

REPO_URL="${RRM_REPO_URL:-https://github.com/phivinhkien1710-sudo/receivable_risk_manager}"
BRANCH="${RRM_BRANCH:-v1.0.0}"
PROJECT="${RRM_PROJECT:-receivables-risk}"
SITENAME="${RRM_SITENAME:-receivables-risk.local}"
HTTP_PORT="${RRM_HTTP_PORT:-8080}"
EMAIL="${RRM_EMAIL:-you@example.com}"
WORKDIR="${RRM_WORKDIR:-$HOME/receivable_risk_manager-install}"

echo "== Receivables Risk Manager installer =="
echo "Project: $PROJECT   Site: $SITENAME   Port: $HTTP_PORT   Work dir: $WORKDIR"
echo

if ! command -v docker >/dev/null 2>&1; then
	cat <<'EOF'
Docker was not found on this computer. Install it first:

- Mac: install Docker Desktop (https://www.docker.com/products/docker-desktop/),
  open it once so it's running, then run this script again.
- Windows: install WSL2 (https://learn.microsoft.com/windows/wsl/install), then
  Docker Desktop with WSL2 integration enabled, then run this script again.
- Linux: Frappe's own installer can install Docker for you automatically —
  it will attempt that in the next step, no action needed here.
EOF
fi

mkdir -p "$WORKDIR"
cd "$WORKDIR"

if [ ! -f easy-install.py ]; then
	echo "Downloading Frappe's installer..."
	curl -fsSL -O https://raw.githubusercontent.com/frappe/bench/develop/easy-install.py
fi

cat >apps.json <<JSON
[
  {
    "url": "${REPO_URL}",
    "branch": "${BRANCH}"
  }
]
JSON

echo "Building and starting everything — this is the slow step (10-20 minutes)..."
python3 easy-install.py build \
	--project "$PROJECT" \
	--apps-json apps.json \
	--app receivable_risk_manager \
	--sitename "$SITENAME" \
	--no-ssl \
	--http-port "$HTTP_PORT" \
	--email "$EMAIL" \
	--deploy

cat <<EOF

== Done ==
Open http://localhost:${HTTP_PORT} in a browser.
Log in as Administrator — the password was saved to ~/passwords.txt on this computer.

Next steps:
  1. Confirm a background worker is running (this app queues imports and AI
     reviews to one - see docs/DEPLOYMENT.md, "The background worker is not
     optional").
  2. Make sure the \`claude\` CLI is reachable BY THAT WORKER, or set an
     absolute path in Risk Settings > AI Review CLI Path.
  3. Review Risk Settings: thresholds, weights, follow_up_days, ai_min_confidence.
  4. Import a CSV via Receivables Import Job, then use its Batch Workflow menu.

See docs/USER_GUIDE.md for day-to-day use.
EOF

#!/usr/bin/env bash
# One-command installer for Receivables Risk Manager.
#
# Wraps Frappe's own official Docker installer (easy-install.py) so a
# non-technical person only has to run this one script instead of the
# multi-step manual process in README.md's "Installing from scratch"
# section (which this script follows exactly — see that section if you
# want to understand what each step below actually does).
#
# This installs the APP ONLY, with no data. The demo dataset is a public,
# non-sensitive benchmark (no customer/contact PII, unlike this developer's
# other app) but is gitignored for repo-size hygiene, so it isn't in this
# clone either — download it from this release's assets and run
# scripts/demo_reset.sh afterwards. See docs/DEMO_SCRIPT.md.
#
# Usage:
#   ./install.sh
#
# Override any default with an environment variable, e.g.:
#   RRM_SITENAME=my-risk.local RRM_HTTP_PORT=8090 ./install.sh

set -euo pipefail

REPO_URL="${RRM_REPO_URL:-https://github.com/phivinhkien1710-sudo/receivable_risk_manager}"
BRANCH="${RRM_BRANCH:-v1.1.0}"
# easy-install.py defaults to Frappe version-16. This app has only ever been
# built and tested against Frappe 15.60 -- pinning to version-15 trades a
# theoretically newer stack for one that's actually been run. Not a data-
# compatibility issue the way it was for this developer's other app (there's
# no existing v15 database being restored here, just a fresh CSV import) --
# just untested-on-16 risk that isn't worth taking right before a demo.
FRAPPE_BRANCH="${RRM_FRAPPE_BRANCH:-version-15}"
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

# Re-running against a project name that already has containers doesn't start
# clean -- easy-install.py regenerates the compose file and runs
# `up --force-recreate` against the EXISTING stack, which fails confusingly
# when the old image no longer matches what the new compose expects.
if command -v docker >/dev/null 2>&1 && [ -n "$(docker ps -aq --filter "name=^${PROJECT}-" 2>/dev/null)" ]; then
	cat <<EOF
A Docker project named "$PROJECT" already exists on this machine.

Re-running the installer against it will not give you a clean install. Either
remove the old one (THIS DELETES ITS DATA):

  docker compose -p $PROJECT -f ~/${PROJECT}-compose.yml down --volumes

or install alongside it under different names:

  RRM_PROJECT=${PROJECT}-2 RRM_SITENAME=${PROJECT}-2.local RRM_HTTP_PORT=8090 ./install.sh

EOF
	exit 1
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

# Python installed from python.org on macOS has no access to the system
# keychain's root certificates, so easy-install.py's HTTPS fetch of
# frappe_docker dies with "CERTIFICATE_VERIFY_FAILED: unable to get local
# issuer certificate" -- and then reports the far more confusing "No such
# file or directory: 'frappe_docker'" as the actual error. Confirmed on a
# real clean Mac while building the equivalent script for this developer's
# other app; this one never had the fix ported over until now.
if [ -z "$(python3 -c 'import ssl; print(ssl.get_default_verify_paths().cafile or "")' 2>/dev/null)" ]; then
	CERTIFI_PEM=$(python3 -c 'import certifi; print(certifi.where())' 2>/dev/null || true)
	if [ -n "$CERTIFI_PEM" ]; then
		export SSL_CERT_FILE="$CERTIFI_PEM"
		export REQUESTS_CA_BUNDLE="$CERTIFI_PEM"
		echo "Note: Python had no CA bundle configured; using certifi's ($CERTIFI_PEM)."
	else
		cat <<'CERTWARN'
WARNING: Python has no root certificates configured and certifi isn't installed,
so the download step below will likely fail with CERTIFICATE_VERIFY_FAILED.
Fix it with either of these, then re-run this script:
  open "/Applications/Python 3.12/Install Certificates.command"
  python3 -m pip install certifi
CERTWARN
	fi
fi

echo "Building and starting everything — this is the slow step (10-20 minutes)..."
python3 easy-install.py build \
	--project "$PROJECT" \
	--apps-json apps.json \
	--frappe-branch "$FRAPPE_BRANCH" \
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

This installed the app with NO DATA. To get the demo dataset:
  1. Download demo_500_open.csv from this repo's Releases page (v1.1.0 assets).
  2. Save it to: apps/receivable_risk_manager/local_data/demo_500_open.csv
  3. Run: ./apps/receivable_risk_manager/scripts/demo_reset.sh $SITENAME

Then see docs/DEMO_SCRIPT.md for the walkthrough, and confirm:
  - Exactly one background worker is running (a second one has caused a
    20x slowdown on AI reviews before -- see docs/DEMO_SCRIPT.md's checklist).
  - The \`claude\` CLI is reachable BY THAT WORKER, or set an absolute path
    in Risk Settings > AI Review CLI Path.
EOF

#!/usr/bin/env bash
# Run on a trusted, fully fetched repository. Never upload findings publicly.
set -euo pipefail

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "Install Gitleaks v8.30.1 (or a reviewed newer security release)." >&2
  exit 2
fi
if [[ "$(git rev-parse --is-shallow-repository)" != false ]]; then
  echo "Refusing shallow clone: fetch all branches, tags and PR refs first." >&2
  exit 2
fi
# Do not print raw secret values. The report stays in the local private workspace.
report="${GITLEAKS_REPORT_PATH:-/tmp/primarykit-history-audit.json}"
gitleaks git --redact --no-banner --log-opts="--all" \
  --report-format json --report-path "$report" .
echo "Automated scan completed. Review report privately, third-party rights and orphaned refs manually."

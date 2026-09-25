#!/usr/bin/env bash
set -euo pipefail

gms_url="${DATAHUB_E2E_GMS_URL:-http://localhost:8080}"
started_quickstart=0

cleanup() {
  if [[ "$started_quickstart" == "1" ]]; then
    uv run datahub docker quickstart --stop
  fi
}
trap cleanup EXIT

if ! curl --fail --silent "$gms_url/config" >/dev/null; then
  quickstart_args=(--version stable --accept-version-default)
  if [[ "$(uname -m)" == "arm64" ]]; then
    quickstart_args+=(--arch arm64)
  fi
  uv run datahub docker quickstart "${quickstart_args[@]}"
  started_quickstart=1
fi

DATAHUB_E2E_GMS_URL="$gms_url" uv run pytest tests/e2e/test_datahub.py -q

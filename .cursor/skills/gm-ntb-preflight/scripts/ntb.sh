#!/usr/bin/env bash
# ntb CLI wrapper - conda env ntb
# Usage: bash .cursor/skills/gm-ntb-preflight/scripts/ntb.sh <subcommand> [args...]
set -euo pipefail

NTB_ENV="${NTB_CONDA_ENV:-ntb}"

if ! command -v conda >/dev/null 2>&1; then
  echo "conda not found" >&2
  exit 1
fi

if ! conda env list | grep -qE "^${NTB_ENV}[[:space:]]"; then
  echo "conda env '${NTB_ENV}' not found" >&2
  exit 1
fi

exec conda run -n "$NTB_ENV" --no-capture-output ntb "$@"

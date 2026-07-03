#!/usr/bin/env bash
# R1-3 preflight
#   bash .cursor/skills/gm-ntb-preflight/scripts/preflight.sh [all|gm|ntb]
set -euo pipefail

FOR="${1:-all}"
TRAIN_REPO="$(cd "$(dirname "$0")/../../../.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GM_WRAPPER="${SCRIPT_DIR}/gm.sh"
NTB_WRAPPER="${SCRIPT_DIR}/ntb.sh"
NTB_ENV="${NTB_CONDA_ENV:-ntb}"
PASS=0
FAIL=0

ok() { echo "  [OK] $1"; PASS=$((PASS + 1)); }
bad() { echo "  [FAIL] $1"; FAIL=$((FAIL + 1)); }

echo "=== R1-3 preflight (scope: $FOR) ==="
echo "Train repo: $TRAIN_REPO"
echo

if [[ "$FOR" == "all" || "$FOR" == "gm" ]]; then
  echo "--- gm ---"
  if bash "$GM_WRAPPER" auth status 2>/dev/null | grep -q '"has_api_key".*true'; then ok "gm has_api_key"; else bad "gm not logged in"; fi
  if bash "$GM_WRAPPER" auth whoami >/dev/null 2>&1; then ok "gm whoami"; else bad "gm whoami failed"; fi
  if bash "$GM_WRAPPER" project list --page 1 --limit 1 >/dev/null 2>&1; then ok "gm project list"; else bad "gm project list failed"; fi
  echo
fi

if [[ "$FOR" == "all" || "$FOR" == "ntb" ]]; then
  echo "--- ntb ---"
  if command -v conda >/dev/null 2>&1; then ok "conda in PATH"; else bad "conda not found"; fi
  if conda env list | grep -qE "^${NTB_ENV}[[:space:]]"; then ok "conda env '$NTB_ENV'"; else bad "conda env '$NTB_ENV' missing"; fi
  if bash "$NTB_WRAPPER" --help 2>/dev/null | grep -q "usage:"; then ok "ntb callable"; else bad "ntb unavailable"; fi
  if bash "$NTB_WRAPPER" health 2>/dev/null | grep -qE '"status".*"ok"|ok'; then ok "ntb health"; else bad "ntb health failed"; fi
  echo
fi

echo "--- training repo ---"
if [[ -f "$TRAIN_REPO/humanoid/scripts/train.py" ]]; then ok "train.py exists"; else bad "train.py missing"; fi
echo

echo "================================"
echo "Result: OK=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]]

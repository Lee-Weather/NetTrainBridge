#!/usr/bin/env bash
# gm CLI wrapper - reads gm-accounts.json when present
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
ACCOUNTS_FILE="${GM_ACCOUNTS_FILE:-$REPO_ROOT/.cursor/skills/gm-ntb-gm-train/gm-accounts.json}"

if ! command -v gm >/dev/null 2>&1; then
  echo "gm CLI not found" >&2
  exit 1
fi

GM_EXTRA=()
if [[ -f "$ACCOUNTS_FILE" ]]; then
  mapfile -t GM_EXTRA < <(python3 - "$ACCOUNTS_FILE" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
base_url = cfg.get("base_url")
api_key = cfg.get("api_key")
if not base_url and not api_key and cfg.get("accounts") and cfg.get("active"):
    acct = cfg["accounts"].get(cfg["active"]) or {}
    base_url = acct.get("base_url")
    api_key = acct.get("api_key")
if base_url:
    print("--base-url")
    print(base_url)
if api_key:
    print("--api-key")
    print(api_key)
PY
  )
fi

exec gm "${GM_EXTRA[@]}" "$@"

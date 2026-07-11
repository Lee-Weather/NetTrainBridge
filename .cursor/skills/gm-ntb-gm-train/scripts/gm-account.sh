#!/usr/bin/env bash
# Verify gm-accounts.json and whoami
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="$SKILL_DIR/gm-accounts.json"
EXAMPLE="$SKILL_DIR/gm-accounts.example.json"
GM_WRAPPER="$SKILL_DIR/../gm-ntb-preflight/scripts/gm.sh"

if [[ ! -f "$CONFIG" ]]; then
  echo "未找到 gm-accounts.json"
  echo "请复制: $EXAMPLE -> $CONFIG"
  exit 1
fi

python3 - "$CONFIG" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
key = cfg.get("api_key", "")
print(f"配置文件: {sys.argv[1]}")
print(f"base_url: {cfg.get('base_url','')}")
print(f"api_key: {'已设置' if key and not key.startswith('<') else '未设置'}")
print()
PY

bash "$GM_WRAPPER" auth whoami

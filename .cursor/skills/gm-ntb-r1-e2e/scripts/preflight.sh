#!/usr/bin/env bash
# R1-3 本机开工检查（训练代码仓库根目录执行）
#   bash .cursor/skills/gm-ntb-r1-e2e/scripts/preflight.sh
set -euo pipefail

TRAIN_REPO="$(cd "$(dirname "$0")/../../../.." && pwd)"
PASS=0
FAIL=0

ok() { echo "  ✅ $1"; PASS=$((PASS + 1)); }
bad() { echo "  ❌ $1"; FAIL=$((FAIL + 1)); }

echo "=== R1-3 preflight（训练仓库）==="
echo "训练仓库: $TRAIN_REPO"
echo

echo "--- 1. CLI（假定 ntb 已安装）---"
if command -v gm >/dev/null 2>&1; then ok "gm 在 PATH"; else bad "未找到 gm"; fi
if command -v ntb >/dev/null 2>&1; then ok "ntb 在 PATH"; else bad "未找到 ntb（请确认已安装且在 PATH）"; fi
echo

echo "--- 2. ntb → Server ---"
if ntb health 2>/dev/null | grep -qE '"status".*"ok"|ok'; then
  ok "ntb health"
else
  bad "ntb health 失败（检查 ntb config / server_url）"
fi
echo

echo "--- 3. gm 认证 ---"
if gm auth status 2>/dev/null | grep -q '"has_api_key".*true'; then ok "gm has_api_key"; else bad "gm 未登录"; fi
if gm auth whoami >/dev/null 2>&1; then ok "gm whoami"; else bad "gm whoami 失败"; fi
echo

echo "--- 4. gm 基础能力 ---"
if gm project list --page 1 --limit 1 >/dev/null 2>&1; then ok "gm project list"; else bad "gm project list 失败"; fi
echo

echo "--- 5. 训练仓库 ---"
if [[ -f "$TRAIN_REPO/humanoid/scripts/train.py" ]]; then
  ok "humanoid/scripts/train.py 存在"
else
  bad "未找到 train.py（请在训练代码仓库根目录使用本 Skill）"
fi
echo

echo "--- 6. 提醒 ---"
echo "  ℹ️  训练机 Agent 须已启动；本机只跑 gm + ntb"
echo

echo "================================"
echo "结果: ✅ ${PASS} 通过  ❌ ${FAIL} 失败"
[[ "${FAIL}" -eq 0 ]]

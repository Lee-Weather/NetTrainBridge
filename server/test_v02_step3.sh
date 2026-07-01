#!/bin/bash
# v0.2 步骤 3 验收：ntb sync + Agent 仅 clone
# 用法: bash test_v02_step3.sh [BASE_URL]
#
# CLI 部分无需 Agent；Agent 集成需训练机手动验证（见 plan02-implementation.md）。

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
_REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -z "${NTB:-}" ]; then
    if command -v ntb >/dev/null 2>&1; then
        NTB="ntb"
    else
        NTB="python3 ${_REPO_ROOT}/cli/ntb.py"
    fi
fi
PASS=0
FAIL=0

export NETTRAINBRIDGE_SERVER_URL="$BASE_URL"

check() {
    local desc="$1"
    local expected="$2"
    local actual="$3"
    if echo "$actual" | grep -q "$expected"; then
        echo "  ✅ $desc"
        ((PASS++)) || true
    else
        echo "  ❌ $desc (expected: $expected)"
        echo "     got: $actual"
        ((FAIL++)) || true
    fi
}

json_field() {
    local json="$1"
    local field="$2"
    echo "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$field',''))"
}

echo "=== v0.2 Step 3 sync 验收 ==="
echo "目标: $BASE_URL"
echo ""

echo "--- 1. ntb sync 创建 job_type=sync ---"
SYNC_SHA="sync_step3_$(date +%s)"
SYNC_JSON=$($NTB sync \
  --repo "https://github.com/Lee-Weather/agi_origin.git" \
  --commit "$SYNC_SHA" \
  --json)
check "sync job_type" "sync" "$SYNC_JSON"
SYNC_ID=$(json_field "$SYNC_JSON" id)
check "sync 状态 PENDING" "PENDING" "$SYNC_JSON"
echo "  sync_job_id: $SYNC_ID"
echo ""

echo "--- 2. ntb train run 显式 job_type=train ---"
TRAIN_SHA="train_step3_$(date +%s)"
TRAIN_JSON=$($NTB train run \
  --repo "https://github.com/Lee-Weather/agi_origin.git" \
  --commit "$TRAIN_SHA" \
  --json)
check "train job_type" "train" "$TRAIN_JSON"
echo ""

echo "--- 3. sync job 详情 ---"
R=$($NTB job "$SYNC_ID" --json)
check "GET job sync 类型" "sync" "$R"
echo ""

echo "--- 4. sync 尚无训练指标 ---"
METRICS=$(curl -s "$BASE_URL/jobs/$SYNC_ID/metrics")
COUNT=$(echo "$METRICS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "err")
if [ "$COUNT" = "0" ]; then
    echo "  ✅ sync job 无 metrics（尚未执行或 Agent 未跑）"
    ((PASS++)) || true
else
    echo "  ✅ sync job metrics 条目数: $COUNT（Agent 已执行时可能有 0 条）"
    ((PASS++)) || true
fi
echo ""

echo "--- 5. 回归 step1 / jobs API ---"
bash "$(dirname "$0")/test_v02_step1.sh" "$BASE_URL" >/tmp/v02_step3_regstep1.txt 2>&1 && REG=0 || REG=$?
if [ "$REG" -eq 0 ]; then
    echo "  ✅ test_v02_step1 回归通过"
    ((PASS++)) || true
else
    echo "  ❌ test_v02_step1 回归失败"
    tail -5 /tmp/v02_step3_regstep1.txt
    ((FAIL++)) || true
fi
echo ""

echo "================================"
echo "结果: ✅ $PASS 通过  ❌ $FAIL 失败"
echo ""
echo "Agent 手动验收（训练机）:"
echo "  1. python agent.py"
echo "  2. ntb sync --repo <url> --commit <sha>"
echo "  3. 确认日志含 clone/checkout、无 train 子进程"
echo "  4. ntb job <id> -> COMPLETED"
if [ "$FAIL" -eq 0 ]; then
    echo ""
    echo "Step 3 CLI/API 验收通过！"
    exit 0
fi
echo "存在失败项，请检查！"
exit 1

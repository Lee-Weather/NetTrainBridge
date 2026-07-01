#!/bin/bash
# v0.2 步骤 8 验收：ntb test run 全流程（Mock sim2sim）
# 用法: bash test_v02_step8_test.sh [BASE_URL]

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
_SERVER_DIR="$(cd "$(dirname "$0")" && pwd)"
_REPO_ROOT="$(cd "$_SERVER_DIR/.." && pwd)"
DATA_DIR="${NETTRAINBRIDGE_DATA_DIR:-$_SERVER_DIR/data}"
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

echo "=== v0.2 Step 8 test run E2E 验收 ==="
echo "目标: $BASE_URL"
echo ""

echo "--- 1. test_with_metrics --self-test ---"
if python3 "$_REPO_ROOT/contrib/agi_origin/humanoid/scripts/test_with_metrics.py" --self-test; then
    echo "  ✅ test_with_metrics self-test"
    ((PASS++)) || true
else
    echo "  ❌ test_with_metrics self-test"
    ((FAIL++)) || true
fi
echo ""

if ! curl -sf "$BASE_URL/health" >/dev/null 2>&1; then
    echo "⚠️  Server 未就绪，跳过 API E2E"
    echo "================================"
    echo "结果: ✅ $PASS 通过  ❌ $FAIL 失败"
    [ "$FAIL" -eq 0 ] && exit 0 || exit 1
fi

echo "--- 2. simulate_step8_e2e（ntb + gm 双路径）---"
if python3 "$_REPO_ROOT/agent/simulate_step8_e2e.py" "$BASE_URL"; then
    echo "  ✅ simulate_step8_e2e"
    ((PASS++)) || true
else
    echo "  ❌ simulate_step8_e2e 失败"
    ((FAIL++)) || true
fi
echo ""

echo "--- 3. metrics kind=test 过滤 ---"
# 取最近一个 COMPLETED test job
TEST_ID=$(curl -s "$BASE_URL/jobs?job_type=test&limit=5" | python3 -c "
import sys, json
jobs = json.load(sys.stdin)
for j in jobs:
    if j.get('status') == 'COMPLETED':
        print(j['id'])
        break
")
if [ -n "$TEST_ID" ]; then
    R=$(curl -s "$BASE_URL/jobs/$TEST_ID/metrics?kind=test")
    check "kind=test 有指标" '"step"' "$R"
    if [ -f "$DATA_DIR/$TEST_ID/test/summary.json" ]; then
        echo "  ✅ Server test/summary.json 存在"
        ((PASS++)) || true
    else
        echo "  ❌ 缺少 $DATA_DIR/$TEST_ID/test/summary.json"
        ((FAIL++)) || true
    fi
else
    echo "  ❌ 未找到 COMPLETED test job"
    ((FAIL++)) || true
fi
echo ""

echo "--- 4. 回归 test_v02_step6 ---"
bash "$_SERVER_DIR/test_v02_step6_fetch.sh" "$BASE_URL" >/tmp/v02_step8_reg.txt 2>&1 && REG=0 || REG=$?
if [ "$REG" -eq 0 ]; then
    echo "  ✅ test_v02_step6 回归通过"
    ((PASS++)) || true
else
    echo "  ❌ test_v02_step6 回归失败"
    tail -10 /tmp/v02_step8_reg.txt
    ((FAIL++)) || true
fi
echo ""

echo "================================"
echo "结果: ✅ $PASS 通过  ❌ $FAIL 失败"
if [ "$FAIL" -eq 0 ]; then
    echo "Step 8 test run 验收通过！"
    exit 0
fi
echo "存在失败项，请检查！"
exit 1

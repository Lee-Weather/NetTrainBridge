#!/bin/bash
# NetTrainBridge CLI 验收脚本（Step 1–3）
# 用法: bash test_cli.sh [BASE_URL]
# 需云服务器已启动；会在服务器上创建临时任务并写入测试数据。

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

echo "=== NetTrainBridge CLI 验收 ==="
echo "目标: $BASE_URL"
echo ""

echo "--- 1. health ---"
R=$($NTB health)
check "ntb health ok" "ok" "$R"
echo ""

echo "--- 2. jobs ---"
R=$($NTB jobs --limit 1)
check "ntb jobs 有输出" "任务列表" "$R"
echo ""

echo "--- 3. 创建测试任务 ---"
JOB_ID=$(curl -s -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d "{\"repo_url\":\"https://github.com/Lee-Weather/agi_origin.git\",\"commit_sha\":\"cli_test_$(date +%s)\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  任务 ID: $JOB_ID"
R=$($NTB job "$JOB_ID")
check "ntb job 状态 PENDING" "PENDING" "$R"
echo ""

echo "--- 4. metrics ---"
curl -s -X POST "$BASE_URL/jobs/$JOB_ID/metrics" \
  -H "Content-Type: application/json" \
  -d '{"metrics":[{"step":1,"loss":0.5,"reward":1.2},{"step":2,"loss":0.3,"reward":1.5}]}' > /dev/null
R=$($NTB metrics "$JOB_ID")
check "ntb metrics 含 step 1" "1" "$R"
check "ntb metrics 含 loss" "0.5000" "$R"
R=$($NTB metrics "$JOB_ID" --since-step 1)
check "ntb metrics --since-step 含 step 2" "2" "$R"
if echo "$R" | grep -qE '^ +1 +'; then
    echo "  ❌ since-step 不应含 step 1 数据行"
    ((FAIL++)) || true
else
    echo "  ✅ since-step 过滤正确"
    ((PASS++)) || true
fi
echo ""

echo "--- 5. heartbeat ---"
curl -s -X POST "$BASE_URL/jobs/$JOB_ID/heartbeat" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"cli-test","gpu_util":88.5,"gpu_mem_used":20000000000,"gpu_mem_total":24000000000}' > /dev/null
R=$($NTB heartbeat "$JOB_ID")
check "ntb heartbeat GPU" "88.5" "$R"
check "ntb heartbeat agent" "cli-test" "$R"
echo ""

echo "--- 6. logs ---"
curl -s -X POST "$BASE_URL/jobs/$JOB_ID/logs" \
  -H "Content-Type: application/json" \
  -d '{"content":"cli test log line 1"}' > /dev/null
curl -s -X POST "$BASE_URL/jobs/$JOB_ID/logs" \
  -H "Content-Type: application/json" \
  -d '{"content":"cli test log line 2"}' > /dev/null
R=$($NTB logs "$JOB_ID" --tail 1)
check "ntb logs --tail 1" "line 2" "$R"
echo ""

echo "--- 7. logs -f (SSE, 4s) ---"
SSE_OUT=$(mktemp)
timeout 4 $NTB logs "$JOB_ID" -f > "$SSE_OUT" &
SSE_PID=$!
sleep 1
curl -s -X POST "$BASE_URL/jobs/$JOB_ID/logs" \
  -H "Content-Type: application/json" \
  -d '{"content":"cli sse live line"}' > /dev/null
sleep 2
wait $SSE_PID 2>/dev/null || true
check "ntb logs -f 可连接" "cli" "$(cat "$SSE_OUT")"
check "ntb logs -f 收到实时日志" "sse live line" "$(cat "$SSE_OUT")"
rm -f "$SSE_OUT"
echo ""

echo "--- 8. --json ---"
R=$($NTB metrics "$JOB_ID" --json)
check "ntb --json 合法数组" "\[" "$R"
echo ""

echo "--- 9. watch --once ---"
R=$($NTB watch "$JOB_ID" --once)
check "ntb watch 标题" "NetTrainBridge watch" "$R"
check "ntb watch 含 step 1" "1" "$R"
check "ntb watch 含 GPU" "88.5" "$R"
check "ntb watch 底部提示" "ntb logs" "$R"
echo ""

echo "--- 10. watch 增量 (8s) ---"
WATCH_OUT=$(mktemp)
PYTHONUNBUFFERED=1 timeout 10 $NTB watch "$JOB_ID" --interval 2 > "$WATCH_OUT" &
WATCH_PID=$!
sleep 2
curl -s -X POST "$BASE_URL/jobs/$JOB_ID/metrics" \
  -H "Content-Type: application/json" \
  -d '{"metrics":[{"step":99,"loss":0.01,"reward":9.9}]}' > /dev/null
sleep 5
wait $WATCH_PID 2>/dev/null || true
check "watch 增量收到 step 99" "99" "$(cat "$WATCH_OUT")"
rm -f "$WATCH_OUT"
echo ""

echo "--- 11. watch --json --once ---"
R=$($NTB watch "$JOB_ID" --once --json)
check "watch --json 含 job" '"job"' "$R"
check "watch --json 含 metrics" '"metrics"' "$R"
echo ""

echo "================================"
echo "结果: ✅ $PASS 通过  ❌ $FAIL 失败"
if [ "$FAIL" -eq 0 ]; then
    echo "CLI 验收通过！"
    exit 0
else
    echo "存在失败项，请检查！"
    exit 1
fi

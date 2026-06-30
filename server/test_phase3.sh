#!/bin/bash
# GradMotion 阶段三验收脚本（平台 API，不需真实训练）
# 使用方法: bash test_phase3.sh [BASE_URL]

BASE_URL="${1:-http://localhost:8000}"
AGI_ORIGIN="https://github.com/Lee-Weather/agi_origin.git"
PASS=0
FAIL=0

check() {
    local desc="$1"
    local expected="$2"
    local actual="$3"
    if echo "$actual" | grep -q "$expected"; then
        echo "  ✅ $desc"
        ((PASS++))
    else
        echo "  ❌ $desc (expected: $expected, got: $actual)"
        ((FAIL++))
    fi
}

echo "=== GradMotion 阶段三验收 ==="
echo "目标: $BASE_URL"
echo ""

# 0. 健康检查
echo "--- 0. 健康检查 ---"
R=$(curl -s "$BASE_URL/health")
check "health" "ok" "$R"
echo ""

# 1. GET /jobs 列表
echo "--- 1. GET /jobs 列表 ---"
R=$(curl -s "$BASE_URL/jobs?limit=10")
check "GET /jobs 返回 JSON 数组" "\[" "$R"
echo ""

# 2. Webhook 模拟 agi_origin push
echo "--- 2. Webhook 模拟 agi_origin push ---"
WEBHOOK_SHA="phase3_$(date +%s)"
R=$(curl -s -X POST "$BASE_URL/webhook/github" \
  -H "X-GitHub-Event: push" \
  -H "Content-Type: application/json" \
  -d "{\"repository\": {\"clone_url\": \"$AGI_ORIGIN\"}, \"after\": \"$WEBHOOK_SHA\", \"ref\": \"refs/heads/main\"}")
check "Webhook accepted" "accepted" "$R"
check "Webhook repo 为 agi_origin" "agi_origin" "$R"
JOB_ID=$(echo "$R" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('job_id',''))" 2>/dev/null)
# accepted 响应无 job_id，从 pending 或 jobs 列表获取
if [ -z "$JOB_ID" ]; then
    sleep 1
    JOB_ID=$(curl -s "$BASE_URL/jobs/pending" | python3 -c "
import sys, json
jobs = json.load(sys.stdin)
for j in jobs:
    if j.get('commit_sha') == '$WEBHOOK_SHA':
        print(j['id']); break
" 2>/dev/null)
fi
if [ -n "$JOB_ID" ]; then
    echo "  任务 ID: $JOB_ID"
    check "pending 列表含新任务" "$JOB_ID" "$(curl -s "$BASE_URL/jobs/pending")"
else
    echo "  ❌ 未能获取 Webhook 创建的任务 ID"
    ((FAIL++))
fi
echo ""

# 3. 指标 API（手动灌入，验证 Dashboard 数据源）
echo "--- 3. 指标 API ---"
if [ -n "$JOB_ID" ]; then
    R=$(curl -s -X POST "$BASE_URL/jobs/$JOB_ID/metrics" \
      -H "Content-Type: application/json" \
      -d '{"metrics":[{"step":100,"loss":0.5,"reward":1.2},{"step":200,"loss":0.3,"reward":1.5}]}')
    check "指标上报 ok" "ok" "$R"
    R=$(curl -s "$BASE_URL/jobs/$JOB_ID/metrics?since_step=100")
    check "since_step 增量查询" "200" "$R"
else
    echo "  ⏭ 跳过（无任务 ID）"
fi
echo ""

# 4. SSE 日志流
echo "--- 4. SSE 日志流 ---"
if [ -n "$JOB_ID" ]; then
    curl -s -X POST "$BASE_URL/jobs/$JOB_ID/logs" \
      -H "Content-Type: application/json" \
      -d '{"content": "phase3 sse test line"}' > /dev/null
    SSE_OUT=$(mktemp)
    timeout 4 curl -N -s "$BASE_URL/jobs/$JOB_ID/logs/stream" > "$SSE_OUT" &
    SSE_PID=$!
    sleep 1
    curl -s -X POST "$BASE_URL/jobs/$JOB_ID/logs" \
      -H "Content-Type: application/json" \
      -d '{"content": "phase3 sse live line"}' > /dev/null
    sleep 2
    wait $SSE_PID 2>/dev/null || true
    check "SSE 流可连接" "data:" "$(cat "$SSE_OUT")"
    check "SSE 包含实时日志" "phase3 sse live line" "$(cat "$SSE_OUT")"
    rm -f "$SSE_OUT"
else
    echo "  ⏭ 跳过（无任务 ID）"
fi
echo ""

# 5. Dashboard 静态页
echo "--- 5. Dashboard 静态页 ---"
CODE=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/static/dashboard.html")
check "dashboard.html 可访问" "200" "$CODE"
CODE=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/static/index.html")
check "index.html 可访问" "200" "$CODE"
echo ""

echo "================================"
echo "结果: ✅ $PASS 通过  ❌ $FAIL 失败"
if [ $FAIL -eq 0 ]; then
    echo "阶段三平台验收通过！"
    echo ""
    echo "完整端到端（需训练机）:"
    echo "  1. agi_origin git push → Webhook 建任务"
    echo "  2. Agent 执行 train_with_metrics.py"
    echo "  3. 打开 $BASE_URL/static/dashboard.html?id={job_id}"
    exit 0
else
    echo "存在失败项，请检查！"
    exit 1
fi

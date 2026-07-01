#!/bin/bash
# v0.2 步骤 6 验收：gm FETCH (5B) + phase API + models/ 上传
# 用法: bash test_v02_step6_fetch.sh [BASE_URL]

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
_SERVER_DIR="$(cd "$(dirname "$0")" && pwd)"
_REPO_ROOT="$(cd "$_SERVER_DIR/.." && pwd)"
DATA_DIR="${NETTRAINBRIDGE_DATA_DIR:-$_SERVER_DIR/data}"
PASS=0
FAIL=0

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

echo "=== v0.2 Step 6 gm FETCH 验收 ==="
echo "目标: $BASE_URL"
echo ""

echo "--- 1. Agent Mock 单元测试 ---"
if python3 "$_REPO_ROOT/agent/test_fetch_mock.py"; then
    echo "  ✅ test_fetch_mock.py"
    ((PASS++)) || true
else
    echo "  ❌ test_fetch_mock.py 失败"
    ((FAIL++)) || true
fi
echo ""

if ! curl -sf "$BASE_URL/health" >/dev/null 2>&1; then
    echo "⚠️  Server 未就绪，跳过 API 集成测试"
    echo "================================"
    echo "结果: ✅ $PASS 通过  ❌ $FAIL 失败"
    [ "$FAIL" -eq 0 ] && exit 0 || exit 1
fi

echo "--- 2. PUT /jobs/{id}/phase ---"
R=$(curl -s -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url":"https://github.com/test/v02-step6-phase.git",
    "commit_sha":"step6_phase",
    "job_type":"test",
    "gm_task_id":"task_phase"
  }')
JOB_ID=$(json_field "$R" id)
R=$(curl -s -X PUT "$BASE_URL/jobs/$JOB_ID/phase" \
  -H "Content-Type: application/json" \
  -d '{"phase":"fetch"}')
check "phase 更新为 fetch" "fetch" "$R"
META=$(curl -s "$BASE_URL/jobs/$JOB_ID/meta")
check "meta phase 同步" "fetch" "$META"
echo ""

echo "--- 3. checkpoint 上传到 models/ ---"
echo "step6 model" > /tmp/step6_model.pt
R=$(curl -s -X POST "$BASE_URL/jobs/$JOB_ID/checkpoint?chunk_index=0&total_chunks=1" \
  -F "file=@/tmp/step6_model.pt")
check "checkpoint 上传完成" "completed" "$R"
if [ -f "$DATA_DIR/$JOB_ID/models/step6_model.pt" ]; then
    echo "  ✅ 文件在 models/ 目录"
    ((PASS++)) || true
else
    echo "  ❌ 期望 $DATA_DIR/$JOB_ID/models/step6_model.pt"
    ((FAIL++)) || true
fi
CODE=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/jobs/$JOB_ID/checkpoint/step6_model.pt")
check "checkpoint 下载 200" "200" "$CODE"
echo ""

echo "--- 4. 回归 test_v02_test_job ---"
bash "$_SERVER_DIR/test_v02_test_job.sh" "$BASE_URL" >/tmp/v02_step6_reg.txt 2>&1 && REG=0 || REG=$?
if [ "$REG" -eq 0 ]; then
    echo "  ✅ test_v02_test_job 回归通过"
    ((PASS++)) || true
else
    echo "  ❌ test_v02_test_job 回归失败"
    tail -15 /tmp/v02_step6_reg.txt
    ((FAIL++)) || true
fi
echo ""

echo "================================"
echo "结果: ✅ $PASS 通过  ❌ $FAIL 失败"
if [ "$FAIL" -eq 0 ]; then
    echo "Step 6 gm FETCH 验收通过！"
    exit 0
fi
echo "存在失败项，请检查！"
exit 1

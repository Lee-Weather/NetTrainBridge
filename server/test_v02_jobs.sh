#!/bin/bash
# v0.2 步骤 2 验收：jobs 表扩展字段与 API
# 用法: bash test_v02_jobs.sh [BASE_URL]

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
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

echo "=== v0.2 Step 2 Jobs API 验收 ==="
echo "目标: $BASE_URL"
echo ""

echo "--- 1. 默认 create（兼容 v0.1）---"
R=$(curl -s -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/test/v02-default.git","commit_sha":"default_sha"}')
check "HTTP 创建成功含 id" '"id"' "$R"
check "默认 job_type=train" "train" "$R"
check "默认 train_source=ntb" "ntb" "$R"
DEFAULT_ID=$(json_field "$R" id)
echo "  job_id: $DEFAULT_ID"
echo ""

echo "--- 2. job_type=sync ---"
R=$(curl -s -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/test/v02-sync.git","commit_sha":"sync_sha","job_type":"sync"}')
check "sync job_type" "sync" "$R"
SYNC_ID=$(json_field "$R" job_type)
check "sync 字段值" "sync" "$SYNC_ID"
echo ""

echo "--- 3. job_type=test + gm_task_id ---"
R=$(curl -s -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url":"https://github.com/test/v02-test.git",
    "commit_sha":"test_gm_sha",
    "job_type":"test",
    "gm_task_id":"task_gm_001"
  }')
check "test job_type" "test" "$R"
check "train_source 自动 gm" "gm" "$R"
check "gm_task_id" "task_gm_001" "$R"
TEST_GM_ID=$(json_field "$R" id)
echo ""

echo "--- 4. job_type=test + parent_train_job_id ---"
R=$(curl -s -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d "{
    \"repo_url\":\"https://github.com/test/v02-test-ntb.git\",
    \"commit_sha\":\"test_ntb_sha\",
    \"job_type\":\"test\",
    \"parent_train_job_id\":\"$DEFAULT_ID\"
  }")
check "test parent_train_job_id" "$DEFAULT_ID" "$R"
check "train_source 自动 ntb" "ntb" "$(json_field "$R" train_source)"
echo ""

echo "--- 5. test 缺关联字段 → 400 ---"
CODE=$(curl -s -o /tmp/v02_test_bad.json -w '%{http_code}' -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/test/bad.git","commit_sha":"x","job_type":"test"}')
check "test 无 gm/parent 返回 400" "400" "$CODE"
echo ""

echo "--- 6. GET /jobs?job_type=test ---"
R=$(curl -s "$BASE_URL/jobs?job_type=test&limit=50")
check "过滤 test 含 gm 任务" "$TEST_GM_ID" "$R"
NON_TEST=$(echo "$R" | python3 -c "
import sys, json
jobs = json.load(sys.stdin)
bad = [j['id'] for j in jobs if j.get('job_type') != 'test']
print(','.join(bad))
" 2>/dev/null)
if [ -n "$NON_TEST" ]; then
    echo "  ❌ test 过滤含非 test job: $NON_TEST"
    ((FAIL++)) || true
else
    echo "  ✅ test 过滤仅含 test job"
    ((PASS++)) || true
fi
echo ""

echo "--- 7. GET /jobs/{id} 新字段 ---"
R=$(curl -s "$BASE_URL/jobs/$TEST_GM_ID")
check "单任务 job_type" "test" "$R"
check "单任务 gm_task_id" "task_gm_001" "$R"
echo ""

echo "================================"
echo "结果: ✅ $PASS 通过  ❌ $FAIL 失败"
if [ "$FAIL" -eq 0 ]; then
    echo "Step 2 Jobs API 验收通过！"
    exit 0
fi
echo "存在失败项，请检查！"
exit 1

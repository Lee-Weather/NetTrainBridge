#!/bin/bash
# v0.2 步骤 9 验收：checkpoint / artifacts API + CLI
# 用法: bash test_v02_artifacts.sh [BASE_URL]

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
_SERVER_DIR="$(cd "$(dirname "$0")" && pwd)"
_REPO_ROOT="$(cd "$_SERVER_DIR/.." && pwd)"

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

md5_file() {
    md5sum "$1" | awk '{print $1}'
}

echo "=== v0.2 Step 9 artifacts 验收 ==="
echo "目标: $BASE_URL"
echo ""

if ! curl -sf "$BASE_URL/health" >/dev/null 2>&1; then
    echo "❌ Server 未就绪: $BASE_URL"
    exit 1
fi

echo "--- 1. checkpoint 列表 API ---"
JOB_JSON=$(curl -s -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/test/v02-art-train.git","commit_sha":"art_train"}')
JOB_ID=$(echo "$JOB_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "step9 checkpoint content" > /tmp/step9_model.pt
ORIG_MD5=$(md5_file /tmp/step9_model.pt)
curl -s -X POST "$BASE_URL/jobs/$JOB_ID/checkpoint?chunk_index=0&total_chunks=1" \
  -F "file=@/tmp/step9_model.pt" > /dev/null
curl -s -X PUT "$BASE_URL/jobs/$JOB_ID/meta" \
  -H "Content-Type: application/json" \
  -d '{"model_filename":"step9_model.pt"}' > /dev/null

R=$(curl -s "$BASE_URL/jobs/$JOB_ID/checkpoint")
check "checkpoint list 含文件名" "step9_model.pt" "$R"
check "primary 标记" "primary" "$R"
check "primary=true" "true" "$R"
echo ""

echo "--- 2. ntb checkpoint list / download ---"
R=$($NTB checkpoint list "$JOB_ID" 2>&1)
check "ntb checkpoint list" "step9_model.pt" "$R"
$NTB checkpoint download "$JOB_ID" -o /tmp/step9_dl.pt >/dev/null
DL_MD5=$(md5_file /tmp/step9_dl.pt)
check "checkpoint MD5 一致" "$ORIG_MD5" "$DL_MD5"
echo ""

echo "--- 3. artifacts API + CLI ---"
TEST_JSON=$(curl -s -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d "{\"repo_url\":\"https://github.com/test/v02-art-test.git\",\"commit_sha\":\"art_test\",\"job_type\":\"test\",\"parent_train_job_id\":\"$JOB_ID\"}")
TEST_ID=$(echo "$TEST_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo '{"mode":"mock"}' > /tmp/step9_summary.json
curl -s -X POST "$BASE_URL/jobs/$TEST_ID/test/summary.json" \
  -F "file=@/tmp/step9_summary.json" > /dev/null
echo '{"step":1,"reward":1.1,"kind":"test"}' > /tmp/step9_metrics.jsonl
curl -s -X POST "$BASE_URL/jobs/$TEST_ID/test/metrics.jsonl" \
  -F "file=@/tmp/step9_metrics.jsonl" > /dev/null

R=$(curl -s "$BASE_URL/jobs/$TEST_ID/artifacts")
check "artifacts list summary" "summary.json" "$R"
check "artifacts list metrics" "metrics.jsonl" "$R"

R=$($NTB artifacts list "$TEST_ID" 2>&1)
check "ntb artifacts list" "summary.json" "$R"

$NTB artifacts download "$TEST_ID" -o /tmp/step9_artifacts.zip >/dev/null
if python3 -c "import zipfile; z=zipfile.ZipFile('/tmp/step9_artifacts.zip'); print('summary.json' in z.namelist())" | grep -q True; then
    echo "  ✅ artifacts zip 含 summary.json"
    ((PASS++)) || true
else
    echo "  ❌ artifacts zip 缺少 summary.json"
    ((FAIL++)) || true
fi
echo ""

echo "--- 4. ntb --help 含 checkpoint/artifacts ---"
R=$($NTB --help 2>&1)
check "help 含 checkpoint" "checkpoint" "$R"
check "help 含 artifacts" "artifacts" "$R"
echo ""

echo "--- 5. 回归 test_v02_step8 ---"
bash "$_SERVER_DIR/test_v02_step8_test.sh" "$BASE_URL" >/tmp/v02_step9_reg.txt 2>&1 && REG=0 || REG=$?
if [ "$REG" -eq 0 ]; then
    echo "  ✅ test_v02_step8 回归通过"
    ((PASS++)) || true
else
    echo "  ❌ test_v02_step8 回归失败"
    tail -10 /tmp/v02_step9_reg.txt
    ((FAIL++)) || true
fi
echo ""

rm -f /tmp/step9_model.pt /tmp/step9_dl.pt /tmp/step9_summary.json /tmp/step9_metrics.jsonl /tmp/step9_artifacts.zip

echo "================================"
echo "结果: ✅ $PASS 通过  ❌ $FAIL 失败"
if [ "$FAIL" -eq 0 ]; then
    echo "Step 9 artifacts 验收通过！"
    exit 0
fi
echo "存在失败项，请检查！"
exit 1

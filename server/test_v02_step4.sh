#!/bin/bash
# v0.2 步骤 4 验收：兜底训练 meta.json
# 用法: bash test_v02_step4.sh [BASE_URL]

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

echo "=== v0.2 Step 4 meta 验收 ==="
echo "目标: $BASE_URL"
echo ""

echo "--- 1. ntb train run 创建 train job ---"
TRAIN_SHA="step4_$(date +%s)"
JOB_JSON=$($NTB train run \
  --repo "https://github.com/Lee-Weather/agi_origin.git" \
  --commit "$TRAIN_SHA" \
  --json)
JOB_ID=$(json_field "$JOB_JSON" id)
check "job_type=train" "train" "$JOB_JSON"
echo "  job_id: $JOB_ID"
echo ""

echo "--- 2. PUT /jobs/{id}/meta（模拟 Agent 训练完成）---"
R=$(curl -s -X PUT "$BASE_URL/jobs/$JOB_ID/meta" \
  -H "Content-Type: application/json" \
  -d "{
    \"job_id\": \"$JOB_ID\",
    \"job_type\": \"train\",
    \"train_source\": \"ntb\",
    \"repo_url\": \"https://github.com/Lee-Weather/agi_origin.git\",
    \"commit_sha\": \"$TRAIN_SHA\",
    \"model_filename\": \"model_test.pt\"
  }")
check "PUT meta train_source" "ntb" "$R"
check "PUT meta model_filename" "model_test.pt" "$R"
echo ""

echo "--- 3. GET /jobs/{id}/meta ---"
R=$(curl -s "$BASE_URL/jobs/$JOB_ID/meta")
check "GET meta train_source" "ntb" "$R"
check "GET meta job_type" "train" "$R"
echo ""

echo "--- 4. meta 合并写入 ---"
R=$(curl -s -X PUT "$BASE_URL/jobs/$JOB_ID/meta" \
  -H "Content-Type: application/json" \
  -d '{"extra_field":"merged_ok"}')
check "meta 合并 extra_field" "merged_ok" "$R"
check "meta 保留 train_source" "ntb" "$R"
echo ""

echo "--- 5. 不存在 job → 404 ---"
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X PUT "$BASE_URL/jobs/no_such_job/meta" \
  -H "Content-Type: application/json" \
  -d '{"train_source":"ntb"}')
check "未知 job PUT meta 404" "404" "$CODE"
echo ""

echo "--- 6. ntb job 展示 meta 字段 ---"
R=$($NTB job "$JOB_ID")
check "ntb job 训练来源" "ntb" "$R"
check "ntb job 模型文件" "model_test.pt" "$R"
echo ""

echo "--- 7. checkpoint 上传仍可用 ---"
echo "step4 meta test" > /tmp/step4_model.pt
curl -s -X POST "$BASE_URL/jobs/$JOB_ID/checkpoint?chunk_index=0&total_chunks=1" \
  -F "file=@/tmp/step4_model.pt" > /dev/null
CODE=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/jobs/$JOB_ID/checkpoint/step4_model.pt")
check "checkpoint 下载 200" "200" "$CODE"
rm -f /tmp/step4_model.pt
echo ""

echo "--- 8. 回归 step3 ---"
bash "$(dirname "$0")/test_v02_step3.sh" "$BASE_URL" >/tmp/v02_step4_reg.txt 2>&1 && REG=0 || REG=$?
if [ "$REG" -eq 0 ]; then
    echo "  ✅ test_v02_step3 回归通过"
    ((PASS++)) || true
else
    echo "  ❌ test_v02_step3 回归失败"
    tail -5 /tmp/v02_step4_reg.txt
    ((FAIL++)) || true
fi
echo ""

echo "================================"
echo "结果: ✅ $PASS 通过  ❌ $FAIL 失败"
if [ "$FAIL" -eq 0 ]; then
    echo "Step 4 验收通过！"
    exit 0
fi
echo "存在失败项，请检查！"
exit 1

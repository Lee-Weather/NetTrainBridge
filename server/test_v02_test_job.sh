#!/bin/bash
# v0.2 步骤 5 验收：test job 骨架 + Server 目录 + ntb test run
# 用法: bash test_v02_test_job.sh [BASE_URL]

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
_SERVER_DIR="$(cd "$(dirname "$0")" && pwd)"
_REPO_ROOT="$(cd "$_SERVER_DIR/.." && pwd)"
DATA_DIR="${NETTRAINBRIDGE_DATA_DIR:-$_SERVER_DIR/data}"

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

check_dir() {
    local desc="$1"
    local path="$2"
    if [ -d "$path" ]; then
        echo "  ✅ $desc"
        ((PASS++)) || true
    else
        echo "  ❌ $desc 不存在: $path"
        ((FAIL++)) || true
    fi
}

echo "=== v0.2 Step 5 test job 验收 ==="
echo "目标: $BASE_URL"
echo "数据目录: $DATA_DIR"
echo ""

if ! curl -sf "$BASE_URL/health" >/dev/null 2>&1; then
    echo "❌ Server 未就绪: $BASE_URL"
    echo "请先启动: cd server && uvicorn main:app --host 0.0.0.0 --port 8000"
    exit 1
fi

echo "--- 1. 创建父 train job ---"
R=$(curl -s -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/test/v02-step5-parent.git","commit_sha":"step5_parent_sha"}')
PARENT_ID=$(json_field "$R" id)
check "父 train job 创建" "$PARENT_ID" "$R"
check_dir "父 job models/" "$DATA_DIR/$PARENT_ID/models"
check_dir "父 job test/" "$DATA_DIR/$PARENT_ID/test"
echo ""

echo "--- 2. test + gm_task_id ---"
R=$(curl -s -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url":"https://github.com/test/v02-step5-gm.git",
    "commit_sha":"step5_gm_sha",
    "job_type":"test",
    "gm_task_id":"task_step5_gm",
    "gm_checkpoint":"latest",
    "load_run":"2026-01-14_09-58-10test_20_video",
    "task":"x1_dh_stand"
  }')
TEST_GM_ID=$(json_field "$R" id)
check "test job_type" "test" "$R"
check "train_source=gm" "gm" "$R"
check "phase=sync" "sync" "$R"
check "gm_task_id" "task_step5_gm" "$R"
check_dir "gm test models/" "$DATA_DIR/$TEST_GM_ID/models"
check_dir "gm test test/" "$DATA_DIR/$TEST_GM_ID/test"
check_dir "gm test videos/" "$DATA_DIR/$TEST_GM_ID/test/videos"
META=$(curl -s "$BASE_URL/jobs/$TEST_GM_ID/meta")
check "meta gm_checkpoint" "latest" "$META"
check "meta load_run" "2026-01-14_09-58-10test_20_video" "$META"
check "meta phase" "sync" "$META"
echo ""

echo "--- 3. test + parent_train_job_id ---"
R=$(curl -s -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d "{
    \"repo_url\":\"https://github.com/test/v02-step5-ntb.git\",
    \"commit_sha\":\"step5_ntb_sha\",
    \"job_type\":\"test\",
    \"parent_train_job_id\":\"$PARENT_ID\",
    \"load_run\":\"2026-01-14_09-58-10test_20_video\",
    \"task\":\"x1_dh_stand\",
    \"checkpoint\":3000
  }")
TEST_NTB_ID=$(json_field "$R" id)
check "parent_train_job_id" "$PARENT_ID" "$R"
check "train_source=ntb" "ntb" "$(json_field "$R" train_source)"
echo ""

echo "--- 4. 校验失败场景 ---"
CODE=$(curl -s -o /tmp/v02_step5_bad1.json -w '%{http_code}' -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/test/bad.git","commit_sha":"x","job_type":"test"}')
check "无 gm/parent → 400" "400" "$CODE"

CODE=$(curl -s -o /tmp/v02_step5_bad2.json -w '%{http_code}' -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url":"https://github.com/test/bad2.git",
    "commit_sha":"x",
    "job_type":"test",
    "gm_task_id":"g1",
    "parent_train_job_id":"'"$PARENT_ID"'"
  }')
check "gm+parent 同时 → 400" "400" "$CODE"

CODE=$(curl -s -o /tmp/v02_step5_bad3.json -w '%{http_code}' -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url":"https://github.com/test/bad3.git",
    "commit_sha":"x",
    "job_type":"test",
    "parent_train_job_id":"nonexistent_job_id",
    "load_run":"bad_load_run",
    "checkpoint":3000
  }')
check "无效 parent → 400" "400" "$CODE"
echo ""

echo "--- 5. ntb test run CLI ---"
R=$($NTB test run --help 2>&1)
check "ntb test run --help" "gm-task-id" "$R"

CLI_GM=$($NTB test run \
  --repo "https://github.com/test/v02-step5-cli-gm.git" \
  --commit "step5_cli_gm" \
  --gm-task-id "task_cli_gm" \
  --load-run "2026-01-14_09-58-10test_20_video" \
  --checkpoint "model_3000.pt" \
  --json)
CLI_GM_ID=$(echo "$CLI_GM" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
check "CLI gm test job_type" "test" "$CLI_GM"
META_CLI=$(curl -s "$BASE_URL/jobs/$CLI_GM_ID/meta")
check "CLI gm_checkpoint" "model_3000.pt" "$META_CLI"

CLI_NTB_OUT=$($NTB test run \
  --repo "https://github.com/test/v02-step5-cli-ntb.git" \
  --commit "step5_cli_ntb" \
  --train-job-id "$PARENT_ID" \
  --load-run "2026-01-14_09-58-10test_20_video" \
  --checkpoint 3000 \
  --json)
check "CLI ntb parent" "$PARENT_ID" "$CLI_NTB_OUT"

R=$($NTB test run \
  --repo "https://github.com/test/x.git" \
  --commit "x" \
  --load-run "2026-01-14_09-58-10test_20_video" 2>&1) && RC=0 || RC=$?
check "CLI 缺 gm/parent 报错" "必须指定" "$R"
echo ""

echo "--- 6. 回归 test_v02_jobs ---"
bash "$_SERVER_DIR/test_v02_jobs.sh" "$BASE_URL" >/tmp/v02_step5_reg_jobs.txt 2>&1 && REG=0 || REG=$?
if [ "$REG" -eq 0 ]; then
    echo "  ✅ test_v02_jobs 回归通过"
    ((PASS++)) || true
else
    echo "  ❌ test_v02_jobs 回归失败"
    tail -20 /tmp/v02_step5_reg_jobs.txt
    ((FAIL++)) || true
fi
echo ""

echo "================================"
echo "结果: ✅ $PASS 通过  ❌ $FAIL 失败"
if [ "$FAIL" -eq 0 ]; then
    echo "Step 5 test job 验收通过！"
    exit 0
fi
echo "存在失败项，请检查！"
exit 1

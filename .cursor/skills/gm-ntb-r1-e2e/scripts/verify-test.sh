#!/usr/bin/env bash
# R1-3 test 验收（本机 ntb CLI，对应 manual §四 A + C）
# 用法: verify-test.sh <test_job_id> [--source gm|ntb] [--commit <sha>]
set -euo pipefail

TEST_ID="${1:-}"
SOURCE="${SOURCE:-gm}"
COMMIT_EXPECT=""
shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE="$2"; shift 2 ;;
    --commit) COMMIT_EXPECT="$2"; shift 2 ;;
    *) shift ;;
  esac
done

if [[ -z "$TEST_ID" ]]; then
  echo "用法: $0 <test_job_id> [--source gm|ntb] [--commit <sha>]"
  exit 1
fi

NTB="${NTB:-ntb}"
PASS=0
FAIL=0
ok() { echo "  ✅ $1"; PASS=$((PASS + 1)); }
bad() { echo "  ❌ $1"; FAIL=$((FAIL + 1)); }

echo "=== R1-3 verify-test ==="
echo "job: $TEST_ID  source: $SOURCE"
echo

JOB=$($NTB job "$TEST_ID" --json 2>/dev/null || echo "{}")
META=$(curl -sf "${NETTRAINBRIDGE_SERVER_URL:-http://127.0.0.1:8000}/jobs/${TEST_ID}/meta" 2>/dev/null || echo "{}")

check_json() {
  local desc="$1" field="$2" expect="$3" json="$4"
  local val
  val=$(echo "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$field',''))" 2>/dev/null || true)
  if [[ "$val" == "$expect" ]]; then ok "$desc ($field=$val)"; else bad "$desc 期望 $expect 得 $val"; fi
}

echo "--- A. 任务状态 ---"
check_json "job_type" "job_type" "test" "$JOB"
check_json "train_source" "train_source" "$SOURCE" "$JOB"
check_json "status" "status" "COMPLETED" "$JOB"
check_json "phase" "phase" "done" "$JOB"

ERR=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error_msg') or '')" 2>/dev/null || true)
if [[ -z "$ERR" ]]; then ok "无 error_msg"; else bad "error_msg: $ERR"; fi

echo "$META" | grep -q "load_run" && ok "meta.load_run" || bad "meta 缺 load_run"
echo "$META" | grep -q "checkpoint" && ok "meta.checkpoint" || bad "meta 缺 checkpoint"

if [[ -n "$COMMIT_EXPECT" ]]; then
  check_json "commit_sha" "commit_sha" "$COMMIT_EXPECT" "$JOB"
fi

if [[ "$SOURCE" == "gm" ]]; then
  GM=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin).get('gm_task_id',''))" 2>/dev/null || true)
  [[ -n "$GM" ]] && ok "gm_task_id 存在" || bad "缺 gm_task_id"
fi

echo "--- C. 指标与产物 ---"
METRICS=$($NTB metrics "$TEST_ID" --json 2>/dev/null || echo "[]")
if echo "$METRICS" | grep -q '"kind".*"test"\|"kind": "test"'; then
  ok "metrics 含 kind=test"
else
  bad "metrics 无 test 指标"
fi
if echo "$METRICS" | grep -q '"mock"'; then
  bad "metrics 含 mock（非真实 sim2sim）"
else
  ok "metrics 无 mock"
fi

ARTS=$($NTB artifacts list "$TEST_ID" 2>/dev/null || true)
echo "$ARTS" | grep -q "summary.json" && ok "artifacts 含 summary.json" || bad "artifacts 无 summary.json"
echo "$ARTS" | grep -q "metrics.jsonl" && ok "artifacts 含 metrics.jsonl" || bad "artifacts 无 metrics.jsonl"

TMPZIP=$(mktemp /tmp/ntb-verify-XXXXXX.zip)
if $NTB artifacts download "$TEST_ID" -o "$TMPZIP" >/dev/null 2>&1; then
  ok "artifacts download"
  SUMMARY=$(unzip -p "$TMPZIP" summary.json 2>/dev/null || true)
  if echo "$SUMMARY" | grep -q '"mode".*"real"'; then
    ok "summary mode=real"
  else
    bad "summary 非 real（可能仍是 mock）"
  fi
  echo "$SUMMARY" | grep -q "success_rate" && ok "summary 含 success_rate" || bad "summary 缺 success_rate"
  echo "$SUMMARY" | grep -q "final_reward" && ok "summary 含 final_reward" || bad "summary 缺 final_reward"
else
  bad "artifacts download 失败"
fi
rm -f "$TMPZIP"

CKPT=$($NTB checkpoint list "$TEST_ID" 2>/dev/null || true)
echo "$CKPT" | grep -q "\.pt" && ok "checkpoint 可列出" || bad "checkpoint 列表无 .pt"

echo
echo "================================"
echo "结果: ✅ ${PASS} 通过  ❌ ${FAIL} 失败"
echo "（训练机路径 B1–B6 需 SSH 到 Agent 机器单独检查）"
[[ "${FAIL}" -eq 0 ]]

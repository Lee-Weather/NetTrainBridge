#!/usr/bin/env bash
# R1-3 test verification
# Usage: bash .cursor/skills/gm-ntb-ntb-test/scripts/verify-test.sh <test_job_id> [--source gm|ntb] [--commit <sha>]
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
  echo "Usage: $0 <test_job_id> [--source gm|ntb] [--commit <sha>]"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NTB_WRAPPER="${NTB_WRAPPER:-${SCRIPT_DIR}/../../gm-ntb-preflight/scripts/ntb.sh}"
PASS=0
FAIL=0
ok() { echo "  [OK] $1"; PASS=$((PASS + 1)); }
bad() { echo "  [FAIL] $1"; FAIL=$((FAIL + 1)); }

echo "=== R1-3 verify-test ==="
echo "job: $TEST_ID  source: $SOURCE"
echo

JOB=$(bash "$NTB_WRAPPER" job "$TEST_ID" --json 2>/dev/null || echo "{}")
META=$(curl -sf "${NETTRAINBRIDGE_SERVER_URL:-http://127.0.0.1:8000}/jobs/${TEST_ID}/meta" 2>/dev/null || echo "{}")

check_json() {
  local desc="$1" field="$2" expect="$3" json="$4"
  local val
  val=$(echo "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$field',''))" 2>/dev/null || true)
  if [[ "$val" == "$expect" ]]; then ok "$desc ($field=$val)"; else bad "$desc expected $expect got $val"; fi
}

echo "--- A. job status ---"
check_json "job_type" "job_type" "test" "$JOB"
check_json "train_source" "train_source" "$SOURCE" "$JOB"
check_json "status" "status" "COMPLETED" "$JOB"
check_json "phase" "phase" "done" "$JOB"

ERR=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error_msg') or '')" 2>/dev/null || true)
if [[ -z "$ERR" ]]; then ok "no error_msg"; else bad "error_msg: $ERR"; fi

echo "$META" | grep -q "load_run" && ok "meta.load_run" || bad "meta missing load_run"
echo "$META" | grep -q "checkpoint" && ok "meta.checkpoint" || bad "meta missing checkpoint"

if [[ -n "$COMMIT_EXPECT" ]]; then
  check_json "commit_sha" "commit_sha" "$COMMIT_EXPECT" "$JOB"
fi

if [[ "$SOURCE" == "gm" ]]; then
  GM=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin).get('gm_task_id',''))" 2>/dev/null || true)
  [[ -n "$GM" ]] && ok "gm_task_id present" || bad "missing gm_task_id"
fi

echo "--- C. metrics & artifacts ---"
METRICS=$(bash "$NTB_WRAPPER" metrics "$TEST_ID" --json 2>/dev/null || echo "[]")
if echo "$METRICS" | grep -q '"kind".*"test"\|"kind": "test"'; then ok "metrics kind=test"; else bad "no test metrics"; fi
if echo "$METRICS" | grep -q '"mock"'; then bad "metrics has mock"; else ok "metrics no mock"; fi

ARTS=$(bash "$NTB_WRAPPER" artifacts list "$TEST_ID" 2>/dev/null || true)
echo "$ARTS" | grep -q "isaac_diag_.*\.csv" && ok "isaac_diag csv" || bad "no isaac_diag csv"
echo "$ARTS" | grep -q "summary.json" && bad "unexpected summary.json" || ok "no summary.json"
echo "$ARTS" | grep -q "metrics.jsonl" && bad "unexpected metrics.jsonl in artifacts" || ok "no metrics.jsonl in artifacts"

TMPZIP=$(mktemp /tmp/ntb-verify-XXXXXX.zip)
if bash "$NTB_WRAPPER" artifacts download "$TEST_ID" -o "$TMPZIP" >/dev/null 2>&1; then
  ok "artifacts download"
  CSV=$(unzip -Z1 "$TMPZIP" 2>/dev/null | grep 'isaac_diag_.*\.csv' | head -1 || true)
  if [[ -n "$CSV" ]]; then
    ok "zip contains csv: $CSV"
    HEADER=$(unzip -p "$TMPZIP" "$CSV" 2>/dev/null | head -1 || true)
    echo "$HEADER" | grep -q "base_lin_vel_x" && ok "csv header valid" || bad "csv header invalid"
  else
    bad "zip missing isaac_diag csv"
  fi
else
  bad "artifacts download failed"
fi
rm -f "$TMPZIP"

CKPT=$(bash "$NTB_WRAPPER" checkpoint list "$TEST_ID" 2>/dev/null || true)
echo "$CKPT" | grep -q "\.pt" && ok "checkpoint listable" || bad "no .pt"

echo
echo "================================"
echo "Result: OK=$PASS FAIL=$FAIL"
[[ "${FAIL}" -eq 0 ]]

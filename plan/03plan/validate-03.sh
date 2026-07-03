#!/usr/bin/env bash
# Plan 03 快速验收：Server meta + CLI 参数
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-http://127.0.0.1:8000}"

pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; exit 1; }

echo "=== Plan 03 validate @ $BASE ==="

cd "$ROOT/agent"
python3 test_plan03.py
python3 test_gm_client.py
python3 test_fetch_mock.py
pass "agent unit tests"

cd "$ROOT/server"
R=$(curl -sf -X POST "$BASE/jobs" -H "Content-Type: application/json" -d '{
  "repo_url":"https://github.com/test/plan03.git",
  "commit_sha":"plan03",
  "job_type":"test",
  "gm_task_id":"task_plan03",
  "load_run":"plan03_load_run",
  "fetch_mode":"server"
}')
JOB=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
META=$(curl -sf "$BASE/jobs/$JOB/meta")
echo "$META" | python3 -c "import sys,json; m=json.load(sys.stdin); assert m.get('fetch_mode')=='server', m" \
  || fail "meta.fetch_mode"
pass "POST test job fetch_mode=server (job $JOB)"

echo ""
echo "Plan 03 validate OK"

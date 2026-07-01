#!/usr/bin/env bash
# R1-2 验收：load_run API + Agent 布局 + 回归 step8
set -euo pipefail

BASE="${1:-http://127.0.0.1:8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

pass=0
fail=0
ok() { echo "  ✅ $1"; pass=$((pass + 1)); }
bad() { echo "  ❌ $1"; fail=$((fail + 1)); }

echo "=== R1-2 验收 ==="
echo "目标: $BASE"
echo

echo "--- 1. checkpoint_layout 单元测试 ---"
if (cd "$ROOT/agent" && python3 test_checkpoint_layout.py); then
  ok "test_checkpoint_layout.py"
else
  bad "test_checkpoint_layout.py"
fi

echo "--- 2. test job 缺 load_run → 400 ---"
CODE=$(curl -s -o /tmp/r1_2_bad.json -w '%{http_code}' -X POST "$BASE/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url":"https://github.com/test/r1-2-bad.git",
    "commit_sha":"bad",
    "job_type":"test",
    "gm_task_id":"task_bad"
  }')
if [[ "$CODE" == "400" ]]; then ok "缺 load_run 400"; else bad "缺 load_run 期望 400 得 $CODE"; fi

echo "--- 3. test job 含 load_run ---"
R=$(curl -s -X POST "$BASE/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url":"https://github.com/test/r1-2-ok.git",
    "commit_sha":"ok",
    "job_type":"test",
    "gm_task_id":"task_r1_2",
    "gm_checkpoint":"latest",
    "load_run":"2026-01-14_09-58-10test_20_video",
    "task":"x1_dh_stand"
  }')
JOB_ID=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || true)
if [[ -n "$JOB_ID" ]]; then
  ok "创建 test job $JOB_ID"
  META=$(curl -s "$BASE/jobs/$JOB_ID/meta")
  echo "$META" | grep -q "2026-01-14_09-58-10test_20_video" && ok "meta.load_run" || bad "meta 无 load_run"
else
  bad "创建 test job 失败: $R"
fi

echo "--- 4. 回归 test_v02_step8 ---"
if bash "$ROOT/server/test_v02_step8_test.sh" "$BASE" 2>&1 | tail -5 | grep -q "验收通过"; then
  ok "test_v02_step8"
else
  bad "test_v02_step8 回归"
fi

echo "--- 5. 回归 test_v02_test_job ---"
if bash "$ROOT/server/test_v02_test_job.sh" "$BASE" 2>&1 | tail -3 | grep -q "验收通过"; then
  ok "test_v02_test_job"
else
  bad "test_v02_test_job 回归"
fi

echo
echo "================================"
echo "结果: ✅ ${pass} 通过  ❌ ${fail} 失败"
[[ "${fail}" -eq 0 ]]

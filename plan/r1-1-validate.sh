#!/usr/bin/env bash
# R1-1 验收：self-test（快）+ 可选真实 play 集成（慢，需 Isaac）
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "$0")/diff/agibot_x1_train-main" && pwd)}"
CONDA_ENV="${NETTRAINBRIDGE_CONDA_ENV:-F1}"

pass=0
fail=0
ok() { echo "  ✅ $1"; pass=$((pass + 1)); }
bad() { echo "  ❌ $1"; fail=$((fail + 1)); }

echo "=== R1-1 test_with_metrics 验收 ==="
echo "工程根: ${ROOT}"
echo

echo "--- 1. --self-test（含 CSV 解析）---"
if (cd "${ROOT}" && python3 humanoid/scripts/test_with_metrics.py --self-test 2>&1); then
  ok "self-test"
else
  bad "self-test"
fi

echo "--- 2. --mock 回归 ---"
TMP=$(mktemp -d)
export NETTRAINBRIDGE_METRICS_FILE="${TMP}/metrics.jsonl"
export NETTRAINBRIDGE_JOB_ID="r1-1-mock"
touch "${TMP}/model.pt"
if (cd "${ROOT}" && python3 humanoid/scripts/test_with_metrics.py \
      --mock --checkpoint "${TMP}/model.pt" --mock-steps 2 2>&1); then
  if [[ -f "${TMP}/test/summary.json" ]]; then
    ok "mock summary"
  else
    bad "mock 缺 summary.json"
  fi
else
  bad "mock 运行失败"
fi
rm -rf "${TMP}"

echo "--- 3. play.py env 常量（RENDER 默认关）---"
if grep -q 'NETTRAINBRIDGE_PLAY_RENDER' "${ROOT}/humanoid/scripts/play.py" \
   && grep -q 'NETTRAINBRIDGE_TEST_OUTPUT_DIR' "${ROOT}/humanoid/scripts/play.py"; then
  ok "play.py 支持 NTB 环境变量"
else
  bad "play.py 未改 env"
fi

if [[ "${RUN_R1_1_ISAAC:-0}" == "1" ]]; then
  echo "--- 4. 真实 sim2sim（Isaac，约 9 分钟）---"
  source "${CONDA_SH:-/home/robot/Anaconda/etc/profile.d/conda.sh}"
  conda activate "${CONDA_ENV}"
  cd "${ROOT}"
  pip install -e . -q
  META="${ROOT}/meta.local.json"
  read -r TASK LOAD_RUN CHECKPOINT <<< "$(python3 -c "
import json
m=json.load(open('${META}'))
print(m['task'], m['load_run'], m['checkpoint'])
")"
  export NETTRAINBRIDGE_METRICS_FILE="${ROOT}/.r1-1-metrics.jsonl"
  export NETTRAINBRIDGE_JOB_ID="r1-1-real"
  rm -f "${NETTRAINBRIDGE_METRICS_FILE}" "${ROOT}/test/summary.json"
  if python3 humanoid/scripts/test_with_metrics.py \
      --task="${TASK}" \
      --load-run="${LOAD_RUN}" \
      --checkpoint="${CHECKPOINT}" \
      --headless 2>&1; then
    if python3 -c "
import json, pathlib, sys
s=json.load(open('${ROOT}/test/summary.json'))
assert s.get('mode')=='real', s
assert s.get('success_rate') is not None
assert pathlib.Path('${ROOT}/test').glob('isaac_diag_*.csv')
"; then
      ok "真实 sim2sim + summary"
    else
      bad "summary 校验失败"
    fi
  else
    bad "真实 sim2sim 失败"
  fi
else
  echo "--- 4. 真实 sim2sim（跳过，设 RUN_R1_1_ISAAC=1 启用）---"
fi

echo
echo "================================"
echo "结果: ✅ ${pass} 通过  ❌ ${fail} 失败"
[[ "${fail}" -eq 0 ]]

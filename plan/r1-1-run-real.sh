#!/usr/bin/env bash
# R1-1 手动跑真实 test_with_metrics（需 F1 + Isaac）
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "$0")/diff/agibot_x1_train-main" && pwd)}"
META="${ROOT}/meta.local.json"
CONDA_ENV="${NETTRAINBRIDGE_CONDA_ENV:-F1}"

read -r TASK LOAD_RUN CHECKPOINT <<< "$(python3 - <<PY
import json
m = json.load(open("${META}"))
print(m["task"], m["load_run"], m["checkpoint"])
PY
)"

source "${CONDA_SH:-/home/robot/Anaconda/etc/profile.d/conda.sh}"
conda activate "${CONDA_ENV}"
cd "${ROOT}"
pip install -e . -q

export NETTRAINBRIDGE_METRICS_FILE="${ROOT}/metrics.jsonl"
export NETTRAINBRIDGE_JOB_ID="r1-1-manual"
export NETTRAINBRIDGE_TEST_OUTPUT_DIR="${ROOT}/test"
export NETTRAINBRIDGE_PLAY_RENDER=0

exec python3 humanoid/scripts/test_with_metrics.py \
  --task="${TASK}" \
  --load-run="${LOAD_RUN}" \
  --checkpoint="${CHECKPOINT}" \
  --headless

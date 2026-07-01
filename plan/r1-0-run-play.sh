#!/usr/bin/env bash
# R1-0 手动跑 play.py（需 conda F1 + Isaac Gym + GPU）
# 用法: bash plan/r1-0-run-play.sh [工程根目录]
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "$0")/diff/agibot_x1_train-main" && pwd)}"
META="${ROOT}/meta.local.json"
CONDA_ENV="${NETTRAINBRIDGE_CONDA_ENV:-F1}"

if [[ ! -f "${META}" ]]; then
  echo "缺少 ${META}，请先完成同窗布局。" >&2
  exit 1
fi

read -r TASK LOAD_RUN CHECKPOINT RUN_NAME <<< "$(python3 - <<PY
import json
m = json.load(open("${META}"))
print(m.get("task", "x1_dh_stand"), m["load_run"], m["checkpoint"], m.get("run_name", "test"))
PY
)"

HEADLESS="${NETTRAINBRIDGE_PLAY_HEADLESS:-1}"
RENDER="${NETTRAINBRIDGE_PLAY_RENDER:-0}"

echo "=== R1-0 手动 play ==="
echo "工程根: ${ROOT}"
echo "task=${TASK} load_run=${LOAD_RUN} checkpoint=${CHECKPOINT} run_name=${RUN_NAME}"
echo "headless=${HEADLESS} render=${RENDER} (无头请保持 render=0)"
echo

source "${CONDA_SH:-/home/robot/Anaconda/etc/profile.d/conda.sh}"
conda activate "${CONDA_ENV}"

cd "${ROOT}"
pip install -e . -q

PLAY_ARGS=(
  humanoid/scripts/play.py
  --task="${TASK}"
  --load_run="${LOAD_RUN}"
  --checkpoint="${CHECKPOINT}"
  --run_name="${RUN_NAME}"
)

if [[ "${HEADLESS}" == "1" ]]; then
  PLAY_ARGS+=(--headless)
fi

# R1-1 前临时：用内联 Python 关 RENDER，避免无头录屏崩溃
export NETTRAINBRIDGE_PLAY_RENDER="${RENDER}"
python3 - <<PY
import os, runpy, sys
os.chdir("${ROOT}")
render = os.environ.get("NETTRAINBRIDGE_PLAY_RENDER", "0") == "1"
# 在 play 模块加载前无法改常量；用 runpy 后改 __main__ 不可靠。
# 首期：直接 exec play，用户需知 headless+默认 RENDER=True 会失败。
sys.argv = [
    "play.py",
    "--task=${TASK}",
    "--load_run=${LOAD_RUN}",
    "--checkpoint=${CHECKPOINT}",
    "--run_name=${RUN_NAME}",
] + (["--headless"] if "${HEADLESS}" == "1" else [])
# 补丁：导入前修改 play 模块常量需在 import 时处理
import importlib.util
spec = importlib.util.spec_from_file_location(
    "play_r1", "${ROOT}/humanoid/scripts/play.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.RENDER = render
mod.LOG_CSV = True
mod.FIX_COMMAND = True
mod.EXPORT_POLICY = False
from humanoid.utils import get_args
args = get_args()
mod.play(args)
PY

echo
echo "若成功，CSV 在: {job_dir}/test/ （R1-1；当前默认仍可能写 /personal/train-more 直至 play 改 env）"

#!/usr/bin/env bash
# R1-0 同窗工程路径自检（不依赖 Isaac / GPU）
# 用法: bash plan/r1-0-validate.sh [工程根目录]
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "$0")/diff/agibot_x1_train-main" && pwd)}"
META="${ROOT}/meta.local.json"

pass=0
fail=0

ok() { echo "  ✅ $1"; pass=$((pass + 1)); }
bad() { echo "  ❌ $1"; fail=$((fail + 1)); }

echo "=== R1-0 同窗布局自检 ==="
echo "工程根: ${ROOT}"
echo

# 1. 训练脚本
if [[ -f "${ROOT}/humanoid/scripts/play.py" ]]; then
  ok "play.py 存在"
else
  bad "缺少 humanoid/scripts/play.py"
fi

if [[ -f "${ROOT}/humanoid/scripts/test_with_metrics.py" ]]; then
  ok "test_with_metrics.py 存在"
else
  bad "缺少 test_with_metrics.py（contrib 未同步时可忽略）"
fi

# 2. meta.local.json
if [[ -f "${META}" ]]; then
  ok "meta.local.json 存在"
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<PY
import json, sys
from pathlib import Path
meta = json.loads(Path("${META}").read_text())
required = ["task", "load_run", "checkpoint", "model_path"]
missing = [k for k in required if not meta.get(k)]
if missing:
    print("  ❌ meta.local.json 缺字段:", ", ".join(missing))
    sys.exit(1)
print("  ✅ meta.local.json 必填字段齐全")
PY
    pass=$((pass + 1))
  fi
else
  bad "缺少 meta.local.json（可复制 diff/agibot_x1_train-main 模板）"
fi

# 3. checkpoint（相对工程根）
MODEL_REL=""
if [[ -f "${META}" ]] && command -v python3 >/dev/null 2>&1; then
  MODEL_REL=$(python3 -c "import json; print(json.load(open('${META}'))['model_path'])")
fi
MODEL_REL="${MODEL_REL:-logs/x1_dh_stand/exported_data/2026-01-14_09-58-10test_20_video/model_3000.pt}"
MODEL="${ROOT}/${MODEL_REL}"

if [[ -f "${MODEL}" ]]; then
  ok "checkpoint 存在: ${MODEL_REL}"
  if command -v md5sum >/dev/null 2>&1; then
    echo "     md5: $(md5sum "${MODEL}" | awk '{print $1}')"
  fi
else
  bad "checkpoint 不存在: ${MODEL_REL}"
  echo "     请将 gm 模型放到: ${ROOT}/logs/x1_dh_stand/exported_data/<load_run>/model_<N>.pt"
fi

# 4. exported_data 层
EXPORTED="${ROOT}/logs/x1_dh_stand/exported_data"
if [[ -d "${EXPORTED}" ]]; then
  ok "logs/x1_dh_stand/exported_data/ 目录存在"
else
  bad "缺少 exported_data 层（play get_load_path 依赖此路径）"
fi

# 5. setup.py / 可安装性
if [[ -f "${ROOT}/setup.py" ]]; then
  ok "setup.py 存在（job 准备阶段需 pip install -e .）"
else
  bad "缺少 setup.py"
fi

echo
echo "================================"
echo "结果: ✅ ${pass} 通过  ❌ ${fail} 失败"
if [[ "${fail}" -gt 0 ]]; then
  exit 1
fi
echo "R1-0 路径自检通过。完整 play 验证: bash plan/r1-0-run-play.sh"

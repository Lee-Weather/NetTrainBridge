#!/bin/bash
# v0.2 步骤 1 验收：CLI 6A（train run / sync 占位 / trigger deprecated）
# 用法: bash test_v02_step1.sh [BASE_URL]
# BASE_URL 可选；若服务器未启动，仅跑本地 help/弃用/sync 占位测试。

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

echo "=== v0.2 Step 1 CLI 验收 ==="

echo "--- 1. help ---"
R=$($NTB train run --help 2>&1)
check "ntb train run --help" "repo" "$R"
R=$($NTB sync --help 2>&1)
check "ntb sync --help" "repo" "$R"
R=$($NTB --help 2>&1)
check "ntb --help 含 train" "train" "$R"
check "ntb --help 含 sync" "sync" "$R"
echo ""

echo "--- 2. trigger deprecated ---"
R=$($NTB trigger --help 2>&1)
check "trigger help 提示弃用" "弃用" "$R"
echo ""

echo "--- 3. sync 创建 job ---"
R=$($NTB sync --repo "https://github.com/Lee-Weather/agi_origin.git" --commit "sync_placeholder_sha" 2>&1) && true
check "ntb sync 创建成功" "type=sync" "$R"
check "ntb sync 提示 ntb job" "ntb job" "$R"
echo ""

SERVER_UP=0
if curl -sf "$BASE_URL/health" >/dev/null 2>&1; then
    SERVER_UP=1
    echo "--- 4. train run 与 trigger 等价（需 Server）---"
    SHA="step1_$(date +%s)"
    REPO="https://github.com/Lee-Weather/agi_origin.git"
    ID_TRAIN=$($NTB train run --repo "$REPO" --commit "$SHA" --json \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
    SHA2="step1_trig_$(date +%s)"
    TRIGGER_OUT=$(mktemp)
    ID_TRIG=$($NTB trigger --repo "$REPO" --commit "$SHA2" --json 2>"$TRIGGER_OUT" \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
    check "trigger stderr 弃用警告" "弃用" "$(cat "$TRIGGER_OUT")"
    rm -f "$TRIGGER_OUT"
    R=$($NTB job "$ID_TRAIN")
    check "train run 创建 PENDING" "PENDING" "$R"
    R=$($NTB job "$ID_TRIG")
    check "trigger 仍创建 PENDING" "PENDING" "$R"
    echo ""
else
    echo "--- 4. 跳过 Server 联调（$BASE_URL 未就绪）---"
    echo ""
fi

echo "================================"
echo "结果: ✅ $PASS 通过  ❌ $FAIL 失败"
if [ "$FAIL" -eq 0 ]; then
    echo "Step 1 CLI 验收通过！"
    exit 0
fi
echo "存在失败项，请检查！"
exit 1

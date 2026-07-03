# R1-3 本机开工检查（Windows PowerShell）
# 在训练代码仓库根目录执行：
#   powershell -ExecutionPolicy Bypass -File .cursor\skills\gm-ntb-r1-e2e\scripts\preflight.ps1
$ErrorActionPreference = "Continue"
$TrainRepo = Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")
$Pass = 0
$Fail = 0

function Ok($msg) { Write-Host "  ✅ $msg"; $script:Pass++ }
function Bad($msg) { Write-Host "  ❌ $msg"; $script:Fail++ }

Write-Host "=== R1-3 preflight（训练仓库 / Windows）==="
Write-Host "训练仓库: $TrainRepo"
Write-Host ""

Write-Host "--- 1. CLI（假定 ntb 已安装）---"
if (Get-Command gm -ErrorAction SilentlyContinue) { Ok "gm 在 PATH" }
else { Bad "未找到 gm（npm i -g @limxdynamics/gm-cli）" }

if (Get-Command ntb -ErrorAction SilentlyContinue) { Ok "ntb 在 PATH" }
else { Bad "未找到 ntb（请确认已安装且已加入 PATH）" }
Write-Host ""

Write-Host "--- 2. ntb → Server ---"
try {
    $health = & ntb health 2>&1 | Out-String
    if ($health -match "ok") { Ok "ntb health" }
    else { Bad "ntb health 失败: $health（检查 ntb config / server_url）" }
} catch {
    Bad "ntb health 失败: $_"
}
Write-Host ""

Write-Host "--- 3. gm 认证 ---"
try {
    $auth = & gm auth status 2>&1 | Out-String
    if ($auth -match "has_api_key.*true") { Ok "gm has_api_key" }
    else { Bad "gm 未登录（gm auth login --api-key ...）" }
    & gm auth whoami | Out-Null
    Ok "gm whoami"
} catch {
    Bad "gm 认证失败: $_"
}
Write-Host ""

Write-Host "--- 4. gm 基础能力 ---"
try {
    & gm project list --page 1 --limit 1 | Out-Null
    Ok "gm project list"
} catch {
    Bad "gm project list 失败"
}
Write-Host ""

Write-Host "--- 5. 训练仓库 ---"
if (Test-Path (Join-Path $TrainRepo "humanoid\scripts\train.py")) {
    Ok "humanoid/scripts/train.py 存在"
} else {
    Bad "未找到 humanoid/scripts/train.py（请在训练代码仓库根目录使用本 Skill）"
}
Write-Host ""

Write-Host "--- 6. 提醒 ---"
Write-Host "  ℹ️  训练机 Agent 须已启动（公司 Linux 机，非本机）"
Write-Host "  ℹ️  Agent config 含 gm_api_key / gm_base_url"
Write-Host ""

Write-Host "================================"
Write-Host "结果: ✅ $Pass 通过  ❌ $Fail 失败"
if ($Fail -gt 0) { exit 1 }

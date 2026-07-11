# Verify gm-accounts.json and call whoami
# Usage: powershell -File .cursor\skills\gm-ntb-gm-train\scripts\gm-account.ps1
$ErrorActionPreference = "Stop"
$SkillDir = Split-Path $PSScriptRoot -Parent
$Example = Join-Path $SkillDir "gm-accounts.example.json"
$Config = Join-Path $SkillDir "gm-accounts.json"
$GmWrapper = Join-Path $SkillDir "..\gm-ntb-preflight\scripts\gm.ps1"

if (-not (Test-Path $Config)) {
    Write-Host "未找到 gm-accounts.json"
    Write-Host "请复制: $Example -> $Config"
    Write-Host "填入 base_url 与 api_key 后重试。"
    exit 1
}

$cfg = Get-Content $Config -Raw | ConvertFrom-Json
$hasKey = $cfg.api_key -and $cfg.api_key -notmatch '^<'
Write-Host "配置文件: $Config"
Write-Host "base_url: $($cfg.base_url)"
Write-Host "api_key: $(if ($hasKey) { '已设置' } else { '未设置' })"
Write-Host ""
& $GmWrapper auth whoami

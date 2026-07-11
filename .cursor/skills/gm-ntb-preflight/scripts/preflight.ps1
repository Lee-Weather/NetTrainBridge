# R1-3 preflight (Windows PowerShell)
# Usage:
#   powershell -ExecutionPolicy Bypass -File .cursor\skills\gm-ntb-preflight\scripts\preflight.ps1
#   powershell -File ...\preflight.ps1 -For gm
#   powershell -File ...\preflight.ps1 -For ntb
param(
    [ValidateSet("all", "gm", "ntb")]
    [string]$For = "all"
)

$ErrorActionPreference = "Continue"
$TrainRepo = Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")
$ScriptDir = $PSScriptRoot
$GmWrapper = Join-Path $ScriptDir "gm.ps1"
$NtbWrapper = Join-Path $ScriptDir "ntb.ps1"
$Pass = 0
$Fail = 0
$NtbEnv = if ($env:NTB_CONDA_ENV) { $env:NTB_CONDA_ENV } else { "ntb" }

function Ok($msg) { Write-Host "  [OK] $msg"; $script:Pass++ }
function Bad($msg) { Write-Host "  [FAIL] $msg"; $script:Fail++ }

function Test-CondaEnvExists([string]$Name) {
    $lines = & conda env list 2>&1
    foreach ($line in $lines) {
        if ($line -match '^\s*(\S+)') {
            if ($Matches[1] -eq $Name) { return $true }
        }
    }
    return $false
}

Write-Host "=== R1-3 preflight (scope: $For) ==="
Write-Host "Train repo: $TrainRepo"
Write-Host ""

if ($For -in @("all", "gm")) {
    Write-Host "--- gm ---"
    if (Test-Path $GmWrapper) { Ok "gm wrapper exists" } else { Bad "gm.ps1 missing" }
    try {
        $auth = & $GmWrapper auth status 2>&1 | Out-String
        if ($auth -match "has_api_key.*true") { Ok "gm has_api_key" }
        else { Bad "gm not logged in" }
        & $GmWrapper auth whoami | Out-Null
        Ok "gm whoami"
        & $GmWrapper project list --page 1 --limit 1 | Out-Null
        Ok "gm project list"
    } catch {
        Bad "gm check failed: $_"
    }
    Write-Host ""
}

if ($For -in @("all", "ntb")) {
    Write-Host "--- ntb ---"
    if (Get-Command conda -ErrorAction SilentlyContinue) { Ok "conda in PATH" }
    else { Bad "conda not found" }
    if (Get-Command conda -ErrorAction SilentlyContinue) {
        if (Test-CondaEnvExists $NtbEnv) { Ok "conda env '$NtbEnv' exists" }
        else { Bad "conda env '$NtbEnv' not found" }
    }
    try {
        $help = & $NtbWrapper --help 2>&1 | Out-String
        if ($help -match "usage:") { Ok "ntb callable via conda" }
        else { Bad "ntb not available in '$NtbEnv'" }
        $health = & $NtbWrapper health 2>&1 | Out-String
        if ($health -match "ok") { Ok "ntb health" }
        else { Bad "ntb health failed" }
    } catch {
        Bad "ntb check failed: $_"
    }
    Write-Host ""
}

Write-Host "--- training repo ---"
if (Test-Path (Join-Path $TrainRepo "humanoid\scripts\train.py")) {
    Ok "humanoid/scripts/train.py exists"
} else {
    Bad "humanoid/scripts/train.py not found"
}
Write-Host ""

Write-Host "--- reminders ---"
Write-Host "  [i] gm: .cursor\skills\gm-ntb-preflight\scripts\gm.ps1"
Write-Host "  [i] ntb: .cursor\skills\gm-ntb-preflight\scripts\ntb.ps1 (or conda activate $NtbEnv)"
if ($For -in @("all", "ntb")) {
    Write-Host "  [i] training machine Agent must be running before ntb test"
}
Write-Host ""

Write-Host "================================"
Write-Host "Result: OK=$Pass FAIL=$Fail"
if ($Fail -gt 0) { exit 1 }

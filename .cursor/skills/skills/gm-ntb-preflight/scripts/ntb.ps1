# ntb CLI wrapper - runs inside conda env "ntb"
# Usage: powershell -File .cursor\skills\gm-ntb-preflight\scripts\ntb.ps1 <subcommand> [args...]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$NtbArgs
)

$ErrorActionPreference = "Stop"
$EnvName = if ($env:NTB_CONDA_ENV) { $env:NTB_CONDA_ENV } else { "ntb" }

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Error "conda not found"
    exit 1
}

$found = $false
foreach ($line in (& conda env list 2>&1)) {
    if ($line -match '^\s*(\S+)') {
        if ($Matches[1] -eq $EnvName) { $found = $true; break }
    }
}
if (-not $found) {
    Write-Error "conda env '$EnvName' not found"
    exit 1
}

& conda run -n $EnvName --no-capture-output ntb @NtbArgs
exit $LASTEXITCODE

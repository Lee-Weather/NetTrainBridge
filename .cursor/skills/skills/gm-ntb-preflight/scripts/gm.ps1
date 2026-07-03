# gm CLI wrapper - reads optional gm-accounts.json for --base-url / --api-key
# Usage: powershell -File .cursor\skills\gm-ntb-preflight\scripts\gm.ps1 task list ...
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$GmArgs
)

$ErrorActionPreference = "Stop"

function Get-GmAccountsPath {
    if ($env:GM_ACCOUNTS_FILE) { return $env:GM_ACCOUNTS_FILE }
    $repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")
    return Join-Path $repoRoot ".cursor\skills\gm-ntb-gm-train\gm-accounts.json"
}

function Get-GmAuthArgs {
    $path = Get-GmAccountsPath
    if (-not (Test-Path $path)) { return @() }

    $config = Get-Content $path -Raw | ConvertFrom-Json
    $baseUrl = $null
    $apiKey = $null

    if ($config.base_url -or $config.api_key) {
        $baseUrl = [string]$config.base_url
        $apiKey = [string]$config.api_key
    } elseif ($config.accounts -and $config.active) {
        $acct = $config.accounts.($config.active)
        if ($acct) {
            $baseUrl = [string]$acct.base_url
            $apiKey = [string]$acct.api_key
        }
    }

    $args = @()
    if ($baseUrl) { $args += @("--base-url", $baseUrl) }
    if ($apiKey) { $args += @("--api-key", $apiKey) }
    return $args
}

$gmCmd = $null
if (Get-Command gm.cmd -ErrorAction SilentlyContinue) {
    $gmCmd = (Get-Command gm.cmd).Source
} elseif (Get-Command gm -ErrorAction SilentlyContinue) {
    $candidate = Get-Command gm
    if ($candidate.CommandType -ne "Alias") { $gmCmd = $candidate.Source }
}
if (-not $gmCmd) {
    Write-Error "gm CLI not found (npm i -g @limxdynamics/gm-cli)"
    exit 1
}

$authArgs = Get-GmAuthArgs
& $gmCmd @authArgs @GmArgs
exit $LASTEXITCODE

# Extract load_run from gm task logs (exported_data path).
# Usage:
#   powershell -File .cursor\skills\gm-ntb-r1\scripts\resolve-load-run.ps1 -TaskId TASK_xxx
#   ... -UpdateRecord   # write load_run into record-run.json
param(
    [Parameter(Mandatory = $true)]
    [string]$TaskId,
    [switch]$UpdateRecord
)

$ErrorActionPreference = "Stop"
$GmWrapper = Join-Path (Split-Path $PSScriptRoot -Parent) "..\gm-ntb-preflight\scripts\gm.ps1"
$GmWrapper = Resolve-Path $GmWrapper

Write-Host "Fetching gm logs for $TaskId ..."
$logs = & $GmWrapper task logs --task-id $TaskId --raw --no-request-log 2>&1 | Out-String
$matches = [regex]::Matches($logs, 'exported_data/([0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}[^/]+)/model_')
if ($matches.Count -eq 0) {
    Write-Error "No load_run found in gm logs. Check task id or gm Web chart paths."
    exit 1
}

$loadRun = $matches[$matches.Count - 1].Groups[1].Value
Write-Host "LOAD_RUN = $loadRun"

if ($UpdateRecord) {
    $recordPath = Join-Path $PSScriptRoot "..\record-run.json"
    if (-not (Test-Path $recordPath)) {
        Write-Error "record-run.json not found: $recordPath"
        exit 1
    }
    $rec = Get-Content $recordPath -Raw | ConvertFrom-Json
    $rec.load_run = $loadRun
    if (-not $rec.gm_task_id) { $rec.gm_task_id = $TaskId }
    if (-not $rec.test_source) { $rec.test_source = "gm" }
    $rec | ConvertTo-Json -Depth 5 | Set-Content $recordPath -Encoding UTF8
    Write-Host "Updated $recordPath"
}

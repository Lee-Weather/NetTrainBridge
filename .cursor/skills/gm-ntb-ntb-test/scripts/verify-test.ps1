# R1-3 test verification (Windows PowerShell)
# Usage: powershell -File .cursor\skills\gm-ntb-ntb-test\scripts\verify-test.ps1 <test_job_id> [-Source gm|ntb] [-Commit <sha>]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$TestId,
    [string]$Source = "gm",
    [string]$Commit = ""
)

$NtbWrapper = Join-Path $PSScriptRoot "..\..\gm-ntb-preflight\scripts\ntb.ps1"
$Pass = 0
$Fail = 0
function Ok($msg) { Write-Host "  [OK] $msg"; $script:Pass++ }
function Bad($msg) { Write-Host "  [FAIL] $msg"; $script:Fail++ }
function Invoke-Ntb { & $NtbWrapper @args }

function Get-JsonField($json, $field) {
    if (-not $json) { return "" }
    try {
        $o = $json | ConvertFrom-Json
        return [string]$o.$field
    } catch { return "" }
}

$server = if ($env:NETTRAINBRIDGE_SERVER_URL) { $env:NETTRAINBRIDGE_SERVER_URL } else { "http://127.0.0.1:8000" }

Write-Host "=== R1-3 verify-test ==="
Write-Host "job: $TestId  source: $Source"
Write-Host ""

$jobJson = Invoke-Ntb job $TestId --json 2>$null
if (-not $jobJson) { $jobJson = "{}" }

try {
    $metaJson = Invoke-RestMethod -Uri "$server/jobs/$TestId/meta" -Method Get
    $metaStr = $metaJson | ConvertTo-Json -Compress
} catch {
    $metaStr = "{}"
}

Write-Host "--- A. job status ---"
if ((Get-JsonField $jobJson "job_type") -eq "test") { Ok "job_type=test" } else { Bad "job_type not test" }
if ((Get-JsonField $jobJson "train_source") -eq $Source) { Ok "train_source=$Source" } else { Bad "train_source mismatch" }
if ((Get-JsonField $jobJson "status") -eq "COMPLETED") { Ok "status=COMPLETED" } else { Bad "status not COMPLETED" }
if ((Get-JsonField $jobJson "phase") -eq "done") { Ok "phase=done" } else { Bad "phase not done" }

$err = Get-JsonField $jobJson "error_msg"
if ([string]::IsNullOrEmpty($err)) { Ok "no error_msg" } else { Bad "error_msg: $err" }

if ($metaStr -match "load_run") { Ok "meta.load_run" } else { Bad "meta missing load_run" }
if ($metaStr -match "checkpoint") { Ok "meta.checkpoint" } else { Bad "meta missing checkpoint" }

if ($Commit -and (Get-JsonField $jobJson "commit_sha") -ne $Commit) {
    Bad "commit_sha mismatch"
} elseif ($Commit) {
    Ok "commit_sha match"
}

if ($Source -eq "gm") {
    if (Get-JsonField $jobJson "gm_task_id") { Ok "gm_task_id present" } else { Bad "missing gm_task_id" }
}

Write-Host "--- C. metrics & artifacts ---"
$metrics = Invoke-Ntb metrics $TestId --json 2>$null
if ($metrics -match "test") { Ok "metrics has test" } else { Bad "metrics no test" }
if ($metrics -match '"mock"') { Bad "metrics has mock" } else { Ok "metrics no mock" }

$arts = Invoke-Ntb artifacts list $TestId 2>$null
if ($arts -match "isaac_diag_.*\.csv") { Ok "artifacts has isaac_diag csv" } else { Bad "no isaac_diag csv" }
if ($arts -match "summary.json") { Bad "unexpected summary.json" } else { Ok "no summary.json" }
if ($arts -match "metrics.jsonl") { Bad "unexpected metrics.jsonl in artifacts" } else { Ok "no metrics.jsonl in artifacts" }

$tmpZip = Join-Path $env:TEMP "ntb-verify-$TestId.zip"
try {
    Invoke-Ntb artifacts download $TestId -o $tmpZip | Out-Null
    Ok "artifacts download"
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($tmpZip)
    $entry = $zip.Entries | Where-Object { $_.Name -match "^isaac_diag_.*\.csv$" } | Select-Object -First 1
    if ($entry) {
        Ok "zip has csv: $($entry.Name)"
        $reader = New-Object System.IO.StreamReader($entry.Open())
        $header = $reader.ReadLine()
        $reader.Close()
        if ($header -match "base_lin_vel_x") { Ok "csv header valid" } else { Bad "csv header invalid" }
    } else {
        Bad "zip missing isaac_diag csv"
    }
    $zip.Dispose()
} catch {
    Bad "artifacts parse failed: $_"
} finally {
    Remove-Item -Force $tmpZip -ErrorAction SilentlyContinue
}

$ckpt = Invoke-Ntb checkpoint list $TestId 2>$null
if ($ckpt -match "\.pt") { Ok "checkpoint listable" } else { Bad "no .pt in checkpoint list" }

Write-Host ""
Write-Host "================================"
Write-Host "Result: OK=$Pass FAIL=$Fail"
if ($Fail -gt 0) { exit 1 }

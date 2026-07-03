# Read and validate record-run.json for mode E (test-only).
# Usage (from training repo root):
#   powershell -File .cursor\skills\gm-ntb-r1\scripts\read-record-run.ps1
#   powershell -File ...\read-record-run.ps1 -ExportEnv
param(
    [string]$RecordPath = "",
    [switch]$ExportEnv,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
$TrainRepo = Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")
if (-not $RecordPath) {
    $RecordPath = Join-Path $PSScriptRoot "..\record-run.json"
}
if (-not (Test-Path $RecordPath)) {
    Write-Error "record-run.json not found: $RecordPath`nCopy from record-run.example.json and fill training outputs."
    exit 1
}

$rec = Get-Content $RecordPath -Raw | ConvertFrom-Json
$source = if ($rec.test_source) { $rec.test_source } elseif ($rec.gm_task_id) { "gm" } elseif ($rec.train_job_id) { "ntb" } else { "" }

$missing = @()
foreach ($f in @("load_run", "checkpoint", "commit_sha")) {
    if (-not $rec.$f) { $missing += $f }
}
if ($source -eq "gm" -and -not $rec.gm_task_id) { $missing += "gm_task_id" }
if ($source -eq "ntb" -and -not $rec.train_job_id) { $missing += "train_job_id" }
if (-not $source) { $missing += "test_source (or gm_task_id / train_job_id)" }

if ($missing.Count -gt 0) {
    Write-Host "[FAIL] Mode E prerequisites missing in record-run.json:"
    $missing | ForEach-Object { Write-Host "  - $_" }
    if ($source -eq "gm" -and $rec.gm_task_id -and -not $rec.load_run) {
        Write-Host "`nHint: resolve load_run from gm logs:"
        Write-Host "  powershell -File .cursor\skills\gm-ntb-r1\scripts\resolve-load-run.ps1 -TaskId $($rec.gm_task_id)"
    }
    exit 1
}

$out = [ordered]@{
    mode         = "E"
    test_source  = $source
    run_name     = $rec.run_name
    task         = if ($rec.task) { $rec.task } else { "x1_dh_stand" }
    commit_sha   = $rec.commit_sha
    gm_task_id   = $rec.gm_task_id
    train_job_id = $rec.train_job_id
    load_run     = $rec.load_run
    checkpoint   = $rec.checkpoint
    test_job_id  = $rec.test_job_id
}

if ($Json) {
    $out | ConvertTo-Json
    exit 0
}

Write-Host "[OK] Mode E ($($out.test_source)) ready"
Write-Host "  LOAD_RUN     = $($out.load_run)"
Write-Host "  CHECKPOINT   = $($out.checkpoint)"
Write-Host "  COMMIT_SHA   = $($out.commit_sha)"
if ($out.gm_task_id) { Write-Host "  GM_TASK_ID   = $($out.gm_task_id)" }
if ($out.train_job_id) { Write-Host "  TRAIN_JOB_ID = $($out.train_job_id)" }
Write-Host "  artifact     = logs/$($out.task)/exported_data/$($out.load_run)/model_$($out.checkpoint).pt"
Write-Host "`nNext: gm-ntb-ntb-test (preflight -For ntb first)"

if ($ExportEnv) {
    $env:LOAD_RUN = $out.load_run
    $env:CHECKPOINT = $out.checkpoint
    $env:COMMIT_SHA = $out.commit_sha
    if ($out.gm_task_id) { $env:GM_TASK_ID = $out.gm_task_id }
    if ($out.train_job_id) { $env:TRAIN_JOB_ID = $out.train_job_id }
}

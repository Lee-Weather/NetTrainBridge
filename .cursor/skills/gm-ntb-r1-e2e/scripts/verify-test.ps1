# R1-3 test 验收（Windows PowerShell）
# 用法: .\verify-test.ps1 <test_job_id> [-Source gm|ntb] [-Commit <sha>]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$TestId,
    [string]$Source = "gm",
    [string]$Commit = ""
)

$Pass = 0
$Fail = 0
function Ok($msg) { Write-Host "  ✅ $msg"; $script:Pass++ }
function Bad($msg) { Write-Host "  ❌ $msg"; $script:Fail++ }

function Get-JsonField($json, $field) {
    if (-not $json) { return "" }
    try {
        $o = $json | ConvertFrom-Json
        return [string]$o.$field
    } catch { return "" }
}

$server = if ($env:NETTRAINBRIDGE_SERVER_URL) { $env:NETTRAINBRIDGE_SERVER_URL } else { "http://127.0.0.1:8000" }

Write-Host "=== R1-3 verify-test（Windows）==="
Write-Host "job: $TestId  source: $Source"
Write-Host ""

$jobJson = & ntb job $TestId --json 2>$null
if (-not $jobJson) { $jobJson = "{}" }

try {
    $metaJson = Invoke-RestMethod -Uri "$server/jobs/$TestId/meta" -Method Get
    $metaStr = $metaJson | ConvertTo-Json -Compress
} catch {
    $metaStr = "{}"
}

Write-Host "--- A. 任务状态 ---"
if ((Get-JsonField $jobJson "job_type") -eq "test") { Ok "job_type=test" } else { Bad "job_type 非 test" }
if ((Get-JsonField $jobJson "train_source") -eq $Source) { Ok "train_source=$Source" } else { Bad "train_source 不匹配" }
if ((Get-JsonField $jobJson "status") -eq "COMPLETED") { Ok "status=COMPLETED" } else { Bad "status 非 COMPLETED" }
if ((Get-JsonField $jobJson "phase") -eq "done") { Ok "phase=done" } else { Bad "phase 非 done" }

$err = Get-JsonField $jobJson "error_msg"
if ([string]::IsNullOrEmpty($err)) { Ok "无 error_msg" } else { Bad "error_msg: $err" }

if ($metaStr -match "load_run") { Ok "meta.load_run" } else { Bad "meta 缺 load_run" }
if ($metaStr -match "checkpoint") { Ok "meta.checkpoint" } else { Bad "meta 缺 checkpoint" }

if ($Commit -and (Get-JsonField $jobJson "commit_sha") -ne $Commit) {
    Bad "commit_sha 与期望不符"
} elseif ($Commit) {
    Ok "commit_sha 一致"
}

if ($Source -eq "gm") {
    if (Get-JsonField $jobJson "gm_task_id") { Ok "gm_task_id 存在" } else { Bad "缺 gm_task_id" }
}

Write-Host "--- C. 指标与产物 ---"
$metrics = & ntb metrics $TestId --json 2>$null
if ($metrics -match "test") { Ok "metrics 含 test" } else { Bad "metrics 无 test" }
if ($metrics -match '"mock"') { Bad "metrics 含 mock" } else { Ok "metrics 无 mock" }

$arts = & ntb artifacts list $TestId 2>$null
if ($arts -match "summary.json") { Ok "artifacts 含 summary.json" } else { Bad "artifacts 无 summary.json" }
if ($arts -match "metrics.jsonl") { Ok "artifacts 含 metrics.jsonl" } else { Bad "artifacts 无 metrics.jsonl" }

$tmpZip = Join-Path $env:TEMP "ntb-verify-$TestId.zip"
try {
    & ntb artifacts download $TestId -o $tmpZip | Out-Null
    Ok "artifacts download"
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($tmpZip)
    $entry = $zip.Entries | Where-Object { $_.Name -eq "summary.json" } | Select-Object -First 1
    if ($entry) {
        $reader = New-Object System.IO.StreamReader($entry.Open())
        $summary = $reader.ReadToEnd()
        $reader.Close()
        if ($summary -match '"mode".*"real"') { Ok "summary mode=real" } else { Bad "summary 非 real" }
        if ($summary -match "success_rate") { Ok "summary 含 success_rate" } else { Bad "summary 缺 success_rate" }
        if ($summary -match "final_reward") { Ok "summary 含 final_reward" } else { Bad "summary 缺 final_reward" }
    } else {
        Bad "zip 内无 summary.json"
    }
    $zip.Dispose()
} catch {
    Bad "artifacts 解析失败: $_"
} finally {
    Remove-Item -Force $tmpZip -ErrorAction SilentlyContinue
}

$ckpt = & ntb checkpoint list $TestId 2>$null
if ($ckpt -match "\.pt") { Ok "checkpoint 可列出" } else { Bad "checkpoint 列表无 .pt" }

Write-Host ""
Write-Host "================================"
Write-Host "结果: ✅ $Pass 通过  ❌ $Fail 失败"
if ($Fail -gt 0) { exit 1 }

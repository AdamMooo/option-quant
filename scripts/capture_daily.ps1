<#
Daily archive capture, for Task Scheduler.

Captures every ticker already in the archive. The tracked set grows by itself —
`main.py TICKER` snapshots any name you look at, and this picks it up the next day.
No watchlist file to keep in sync.

Registration command is in options-quant.md under "Scheduled capture".
#>

$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$log  = Join-Path $repo "logs\capture-$(Get-Date -Format 'yyyy-MM').log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

function Write-Log($msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg" | Add-Content -Path $log
}

# Weekends are skippable by rule. Market holidays are not — that would need a
# hardcoded table, and a stale table fails silently. A holiday run appends a
# snapshot carrying the previous session's quote_date, which iv30_series already
# dedupes by quote_date; the cost is disk, not correctness.
$dow = (Get-Date).DayOfWeek
if ($dow -eq 'Saturday' -or $dow -eq 'Sunday') {
    Write-Log "skipped ($dow)"
    exit 0
}

$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Log "FAILED: no venv at $python"
    exit 1
}

Set-Location $repo
Write-Log "capture start"

$output = & $python archive.py capture --from-archive 2>&1
$code = $LASTEXITCODE

$output | ForEach-Object { Write-Log "  $_" }
Write-Log "capture end (exit $code)"

exit $code

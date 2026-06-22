$ErrorActionPreference = "Continue"

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$PSDefaultParameterValues["Out-File:Encoding"] = "utf8"
$PSDefaultParameterValues["Set-Content:Encoding"] = "utf8"
$PSDefaultParameterValues["Add-Content:Encoding"] = "utf8"

$Root = Split-Path -Parent $PSScriptRoot
$PythonCandidates = @(
    "C:\Users\mobu3\AppData\Local\Programs\Python\Python313\python.exe",
    "C:\Users\mobu3\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)
$Python = $PythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Python) {
    throw "Python executable was not found."
}

$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogPath = Join-Path $LogDir "daily_collection_$Stamp.log"

function Run-Step {
    param(
        [string]$Name,
        [string]$Script
    )
    Write-Host "[$(Get-Date -Format s)] START $Name"
    "[$(Get-Date -Format s)] START $Name" | Out-File -FilePath $LogPath -Append -Encoding utf8
    & $Python $Script 2>&1 | ForEach-Object {
        $Line = $_.ToString()
        Write-Host $Line
        $Line | Out-File -FilePath $LogPath -Append -Encoding utf8
    }
    if ($LASTEXITCODE -ne 0) {
        "[$(Get-Date -Format s)] WARN $Name failed with exit code $LASTEXITCODE" | Out-File -FilePath $LogPath -Append -Encoding utf8
    } else {
        "[$(Get-Date -Format s)] DONE $Name" | Out-File -FilePath $LogPath -Append -Encoding utf8
    }
}

Run-Step "fx data" "$PSScriptRoot\collect_fx_data.py"
Run-Step "naver news search data" "$PSScriptRoot\collect_naver_news_search.py"
$env:NAVER_INVESTOR_FLOW_MAX_PAGES = "1"
$env:NAVER_INVESTOR_FLOW_MERGE_EXISTING = "1"
$env:NAVER_INVESTOR_FLOW_TIMEOUT_SECONDS = "8"
$env:NAVER_INVESTOR_FLOW_MAX_CONSECUTIVE_ERRORS = "25"
Run-Step "naver investor flow data" "$PSScriptRoot\collect_naver_investor_flows.py"
Remove-Item Env:NAVER_INVESTOR_FLOW_MAX_PAGES -ErrorAction SilentlyContinue
Remove-Item Env:NAVER_INVESTOR_FLOW_MERGE_EXISTING -ErrorAction SilentlyContinue
Remove-Item Env:NAVER_INVESTOR_FLOW_TIMEOUT_SECONDS -ErrorAction SilentlyContinue
Remove-Item Env:NAVER_INVESTOR_FLOW_MAX_CONSECUTIVE_ERRORS -ErrorAction SilentlyContinue
$env:KIS_INVESTOR_FLOW_SLEEP_SECONDS = "0.06"
Run-Step "KIS investor flow overlay" "$PSScriptRoot\collect_kis_investor_flows.py"
Remove-Item Env:KIS_INVESTOR_FLOW_SLEEP_SECONDS -ErrorAction SilentlyContinue
Run-Step "pykrx fallback market data" "$PSScriptRoot\collect_pykrx_data.py"
Run-Step "OpenDART disclosures" "$PSScriptRoot\collect_dart_disclosures.py"
$env:KRX_DATE_PERIODS = "30"
$env:KRX_REQUEST_TIMEOUT_SECONDS = "12"
$env:KRX_MAX_RUNTIME_SECONDS = "150"
Run-Step "KRX official data" "$PSScriptRoot\collect_krx_openapi.py"
Remove-Item Env:KRX_DATE_PERIODS -ErrorAction SilentlyContinue
Remove-Item Env:KRX_REQUEST_TIMEOUT_SECONDS -ErrorAction SilentlyContinue
Remove-Item Env:KRX_MAX_RUNTIME_SECONDS -ErrorAction SilentlyContinue
Run-Step "KIS intraday close snapshot" "$PSScriptRoot\collect_kis_intraday.py"
$KisSummaryPath = Join-Path $Root "reports\kis_intraday_collection_summary.json"
if (Test-Path $KisSummaryPath) {
    try {
        $KisSummary = Get-Content $KisSummaryPath -Raw -Encoding utf8 | ConvertFrom-Json
        $SuccessfulRows = 0
        if ($null -ne $KisSummary.successful_rows) {
            $SuccessfulRows = [int]$KisSummary.successful_rows
        }
        if ($KisSummary.status -eq "skipped_non_trading_day") {
            "[$(Get-Date -Format s)] SKIP realtime close fallback on non-trading day" | Out-File -FilePath $LogPath -Append -Encoding utf8
        } elseif (($KisSummary.status -ne "ok") -or ($SuccessfulRows -lt 200)) {
            Run-Step "Naver realtime fallback close snapshot" "$PSScriptRoot\collect_naver_realtime.py"
        }
    } catch {
        Run-Step "Naver realtime fallback close snapshot" "$PSScriptRoot\collect_naver_realtime.py"
    }
}
Run-Step "Kaggle global market factors" "$PSScriptRoot\collect_kaggle_global_market_data.py"
Run-Step "sector model v2 training" "$PSScriptRoot\train_sector_return_model_v2.py"
Run-Step "sector rank model v3 training" "$PSScriptRoot\train_sector_rank_model_v3.py"
Run-Step "sector rank model v4 training" "$PSScriptRoot\train_sector_rank_model_v4.py"
Run-Step "sector rank model v5 training" "$PSScriptRoot\train_sector_rank_model_v5.py"
Run-Step "portfolio advisor report" "$PSScriptRoot\build_advisor_report.py"
Run-Step "intraday model learning state" "$PSScriptRoot\update_intraday_learning_state.py"
Run-Step "intraday rebound timing signals" "$PSScriptRoot\build_intraday_rebound_signals.py"
Run-Step "intraday rebound ML model" "$PSScriptRoot\train_intraday_rebound_model.py"
Run-Step "weekend/search attention effects" "$PSScriptRoot\compute_weekend_signal_effects.py"
Run-Step "FOMO blend weight tuning" "$PSScriptRoot\tune_fomo_blend_weights.py"
Run-Step "tomorrow sector prediction" "$PSScriptRoot\build_tomorrow_prediction.py"
Run-Step "prediction snapshot archive" "$PSScriptRoot\create_prediction_snapshot.py"
Run-Step "prediction accuracy evaluation" "$PSScriptRoot\evaluate_prediction_accuracy.py"
Run-Step "panic rebound watch shadow tracking" "$PSScriptRoot\track_panic_rebound_watch_shadow.py"
Run-Step "final blend shadow tuning" "$PSScriptRoot\tune_final_blend_weights.py"
Run-Step "meta action filter shadow tracking" "$PSScriptRoot\track_meta_action_filter_shadow.py"
Run-Step "shadow rank model v6 tracking" "$PSScriptRoot\track_shadow_rank_model_v6.py"
Run-Step "model issue diagnosis" "$PSScriptRoot\diagnose_prediction_issues.py"

Write-Host "Daily pipeline finished. Log: $LogPath"

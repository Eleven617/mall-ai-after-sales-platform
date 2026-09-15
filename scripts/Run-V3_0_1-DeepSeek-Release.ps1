param(
    [string]$ReleaseId = "",
    [string]$RuntimeCommit = "",
    [string]$Report = "tmp/deepseek-v3.0.1-candidate.json",
    [string]$Lock = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "mall-ai-service\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "FastAPI virtual environment is missing" }

if ([string]::IsNullOrWhiteSpace($RuntimeCommit)) {
    $RuntimeCommit = (& git -C $root rev-parse HEAD).Trim()
}
if ([string]::IsNullOrWhiteSpace($ReleaseId)) {
    $ReleaseId = "v3.0.1-final-$RuntimeCommit"
}
if ([string]::IsNullOrWhiteSpace($Lock)) {
    $Lock = "docs/evidence/deepseek-release-lock-v3.0.1-final-$RuntimeCommit.json"
}

# A fresh process-only password is used to create disposable Java fixtures.
# It is never written to the repository, report, console, or Git history.
$temporaryPassword = "LocalSynthetic-" + ([guid]::NewGuid().ToString("N"))
$env:MALL_LIVE_DEMO_PASSWORD = $temporaryPassword
$env:MALL_JAVA_BASE_URL = "http://127.0.0.1:8085"
$env:MALL_DEMO_WEB_BASE_URL = "http://127.0.0.1:5173"
$env:MALL_RUNTIME_PROVIDER_MODE = "live"
$env:MALL_RUNTIME_COMMIT = $RuntimeCommit
$env:MALL_IMAGE_REVISION = $RuntimeCommit
$env:MALL_PROMPT_VERSION = "agent_runtime_v3_3"
$env:MALL_SCHEMA_VERSION = "task_runtime_v3_0"

$reportPath = Join-Path $root $Report
$lockPath = Join-Path $root $Lock
Push-Location (Join-Path $root "mall-ai-service")
try {
    & $python "scripts\run_deepseek_release_batch.py" `
        --phase candidate `
        --release-id $ReleaseId `
        --runtime-commit $RuntimeCommit `
        --report $reportPath `
        --lock $lockPath
    exit $LASTEXITCODE
}
finally {
    Pop-Location
    Remove-Item Env:MALL_LIVE_DEMO_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:MALL_JAVA_BASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:MALL_DEMO_WEB_BASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:MALL_RUNTIME_PROVIDER_MODE -ErrorAction SilentlyContinue
    Remove-Item Env:MALL_RUNTIME_COMMIT -ErrorAction SilentlyContinue
    Remove-Item Env:MALL_IMAGE_REVISION -ErrorAction SilentlyContinue
    Remove-Item Env:MALL_PROMPT_VERSION -ErrorAction SilentlyContinue
    Remove-Item Env:MALL_SCHEMA_VERSION -ErrorAction SilentlyContinue
}

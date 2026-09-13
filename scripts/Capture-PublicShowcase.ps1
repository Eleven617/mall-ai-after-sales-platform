$ErrorActionPreference = 'Stop'

# Public capture entry point.  It deliberately refuses to fabricate a showcase
# when the real provider is unavailable.  The browser helper stays in tmp/ so
# raw frames, temporary credentials and local fixture files remain ignored.
$root = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $root 'tmp\run_fresh_capture.ps1'
$python = Join-Path $root 'mall-ai-service\.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $runner)) {
    throw 'tmp/run_fresh_capture.ps1 is missing; restore the local capture runner before recording.'
}
if (-not (Test-Path -LiteralPath $python)) {
    throw 'mall-ai-service/.venv is missing; prepare the local demo environment first.'
}
if ([string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
    throw 'DEEPSEEK_API_KEY is required in the local process environment; it is never read from the repository or printed.'
}

try {
    $serverVersion = docker info --format '{{.ServerVersion}}' 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($serverVersion)) {
        throw 'Docker Engine is unavailable.'
    }
    Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5173' -TimeoutSec 10 | Out-Null

    # The ignored runner creates a one-shot synthetic identity/order and calls
    # the local CDP helper. It must exit non-zero on provider failure or any
    # missing business state; no failed frame is copied into the final folder.
    & $runner
    if ($LASTEXITCODE -ne 0) {
        throw "browser capture failed with exit code $LASTEXITCODE"
    }
}
finally {
    Remove-Item Env:MALL_CAPTURE_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:MALL_CAPTURE_USER -ErrorAction SilentlyContinue
    Remove-Item Env:MALL_CAPTURE_FIXTURE -ErrorAction SilentlyContinue
}

$targets = @(
    'docs/assets/showcase-final/main-open-task-closed-loop.gif',
    'docs/assets/showcase-final/clarify-pause-resume.gif',
    'docs/assets/showcase-final/fact-change-replan-handoff.gif'
)
$missing = $targets | Where-Object { -not (Test-Path -LiteralPath (Join-Path $root $_)) }
if ($missing) {
    throw ('capture completed without all required final showcase assets: ' + ($missing -join ', '))
}
Write-Output 'Public showcase capture completed; inspect every frame and record hashes before staging assets.'

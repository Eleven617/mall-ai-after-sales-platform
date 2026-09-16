param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$RuntimeCommit,
    [string]$Report = 'tmp/v3.0.3-slow-gateway.json',
    [string]$BatchId = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'mall-ai-service\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'FastAPI virtual environment is missing' }
if ([string]::IsNullOrWhiteSpace($BatchId)) { $BatchId = 'v3.0.3-offline-slow-' + ([guid]::NewGuid().ToString('N').Substring(0, 12)) }

# Keep v3.0.3 evidence in an isolated ignored ledger; v3.0.2 historical
# reports and their 0-vs-9 discrepancy remain byte-for-byte unchanged.
$ledgerDirectory = Join-Path $root 'tmp\release-ledger-v3.0.3-slow'
New-Item -ItemType Directory -Force -Path $ledgerDirectory | Out-Null
$env:MALL_RELEASE_LEDGER_HOST_PATH = './tmp/release-ledger-v3.0.3-slow'
$env:MALL_RELEASE_LEDGER_PATH = Join-Path $ledgerDirectory 'ledger.jsonl'
$env:MALL_RUNTIME_PROVIDER_MODE = 'deterministic'
$env:MALL_RUNTIME_COMMIT = $RuntimeCommit
$env:MALL_IMAGE_REVISION = $RuntimeCommit
$env:MALL_PROMPT_VERSION = 'agent_runtime_v3_3'
$env:MALL_SCHEMA_VERSION = 'task_runtime_v3_0'
$env:MALL_DETERMINISTIC_PROVIDER_DELAY_SECONDS = '38'
$env:PYTHONPATH = Join-Path $root 'mall-ai-service'

$temporaryPassword = 'LocalSynthetic-' + ([guid]::NewGuid().ToString('N'))
$env:MALL_LIVE_DEMO_PASSWORD = $temporaryPassword
$env:MALL_JAVA_BASE_URL = 'http://127.0.0.1:8085'
$env:MALL_DEMO_WEB_BASE_URL = 'http://127.0.0.1:5173'
$secureTemporaryPassword = ConvertTo-SecureString $temporaryPassword -AsPlainText -Force
& (Join-Path $root 'scripts\Initialize-LocalDemoAccess.ps1') -DemoPassword $secureTemporaryPassword -PrepareCustomerFixtures | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Local synthetic demo identity bootstrap failed.' }
$secureTemporaryPassword = $null

Push-Location $root
try {
    & docker compose build mall-ai-service mall-ai-web
    if ($LASTEXITCODE -ne 0) { throw 'Slow-gate images failed to build.' }
    & docker compose up -d --force-recreate mall-ai-service mall-ai-web
    if ($LASTEXITCODE -ne 0) { throw 'Slow-gate services failed to start.' }
    Push-Location (Join-Path $root 'mall-ai-service')
    try {
        & $python 'scripts\run_v3_0_2_slow_gateway_test.py' --report (Join-Path $root $Report) --batch-id $BatchId
        exit $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location
    Remove-Item Env:MALL_LIVE_DEMO_PASSWORD,Env:MALL_JAVA_BASE_URL,Env:MALL_DEMO_WEB_BASE_URL,Env:MALL_RUNTIME_PROVIDER_MODE,Env:MALL_RUNTIME_COMMIT,Env:MALL_IMAGE_REVISION,Env:MALL_PROMPT_VERSION,Env:MALL_SCHEMA_VERSION,Env:MALL_DETERMINISTIC_PROVIDER_DELAY_SECONDS,Env:PYTHONPATH,Env:MALL_RELEASE_LEDGER_HOST_PATH,Env:MALL_RELEASE_LEDGER_PATH -ErrorAction SilentlyContinue
}

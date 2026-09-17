param(
    [ValidateSet('Preflight', 'BatchA', 'BatchB')]
    [string]$Phase = 'Preflight',
    [string]$ReleaseId = 'mall-v3.0.3-portfolio-final-3a0d59080e94',
    [string]$RuntimeCommit = '3a0d59080e94848553ac2d981116acf236df3cf6'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'mall-ai-service\.venv\Scripts\python.exe'
$ledgerDirectory = Join-Path $root 'tmp\release-ledger-portfolio-final'
$ledgerPath = Join-Path $ledgerDirectory 'ledger.jsonl'
$lockPath = Join-Path $root "docs\evidence\deepseek-release-lock-$ReleaseId.json"
$reportDirectory = Join-Path $root 'tmp\portfolio-final-release'
$reportName = if ($Phase -eq 'BatchA') { 'batch-a.json' } elseif ($Phase -eq 'BatchB') { 'batch-b.json' } else { 'preflight.json' }
$reportPath = Join-Path $reportDirectory $reportName

if (-not (Test-Path -LiteralPath $python)) { throw 'mall-ai-service/.venv is missing.' }
if ($RuntimeCommit -notmatch '^[0-9a-f]{40}$') { throw 'RuntimeCommit must be a full SHA.' }
if ((& git -C $root branch --show-current).Trim() -ne 'codex/v3.0.3-confirmation-contract') { throw 'The portfolio candidate branch is not checked out.' }
& git -C $root merge-base --is-ancestor $RuntimeCommit HEAD
if ($LASTEXITCODE -ne 0) { throw 'Runtime commit is not an ancestor of HEAD.' }
if ((& git -C $root status --porcelain).Length -gt 0) { throw 'Working tree must be committed before a paid batch.' }

function Disable-LiveAuthorization {
    $env:MALL_RUNTIME_COMMIT = $RuntimeCommit
    $env:MALL_IMAGE_REVISION = $RuntimeCommit
    $env:MALL_RUNTIME_PROVIDER_MODE = 'live'
    $env:MALL_PROVIDER_LIVE_AUTH = '0'
    $env:MALL_RELEASE_ID = ''
    $env:MALL_RELEASE_BATCH_ID = ''
    $env:MALL_RELEASE_LEDGER_HOST_PATH = $ledgerDirectory
    $env:MALL_RELEASE_LEDGER_CONTAINER_PATH = '/app/release-ledger/ledger.jsonl'
    docker compose up -d --no-deps --force-recreate mall-ai-service | Out-Null
}

function Assert-ContainerIdentity {
    $version = Invoke-RestMethod 'http://127.0.0.1:8000/health/version'
    if ($version.runtimeCommit -ne $RuntimeCommit -or $version.imageRevision -ne $RuntimeCommit -or $version.providerMode -ne 'live' -or $version.model -ne 'deepseek-flash') {
        throw 'Running AI service does not match the reviewed live runtime identity.'
    }
    $actual = @(docker compose ps --format '{{.Service}}|{{.State}}|{{.Health}}')
    foreach ($service in @('mysql', 'mongo', 'redis', 'rabbitmq', 'mall-portal', 'mall-admin', 'mall-ai-service', 'mall-ai-web')) {
        if ($actual -notcontains "$service|running|healthy") {
            throw "Compose service is not healthy: $service"
        }
    }
}

New-Item -ItemType Directory -Force -Path $ledgerDirectory, $reportDirectory | Out-Null
Disable-LiveAuthorization
Assert-ContainerIdentity

# This only invokes the in-process guard. It does not instantiate a provider
# client or open a network socket.
docker compose exec -T mall-ai-service python -c "from app.services.provider_guard import assert_provider_request_allowed,ProviderGuardError; assert_provider_request_allowed('https://api.deepseek.com')" 2>$null
if ($LASTEXITCODE -eq 0) { throw 'Provider Guard unexpectedly allowed an unauthorised request.' }

if ($Phase -eq 'Preflight') {
    if (Test-Path -LiteralPath $lockPath) { throw 'A portfolio release lock already exists.' }
    if (Test-Path -LiteralPath $ledgerPath) { throw 'The dedicated portfolio ledger is not empty.' }
    $preflight = @{ status = 'passed'; providerRequests = 0; runtimeCommit = $RuntimeCommit; releaseId = $ReleaseId; ledgerEmpty = $true } | ConvertTo-Json -Compress
    Set-Content -LiteralPath $reportPath -Value $preflight -Encoding ascii
    Write-Output $preflight
    exit 0
}

if ($Phase -eq 'BatchA') {
    if (Test-Path -LiteralPath $lockPath) { throw 'Batch A is already consumed or locked.' }
    if (Test-Path -LiteralPath $ledgerPath) { throw 'Batch A requires a fresh dedicated ledger.' }
    $pythonPhase = 'portfolio_a'
} else {
    if (-not (Test-Path -LiteralPath $lockPath)) { throw 'Batch B requires a successful Batch A lock.' }
    $lock = Get-Content -Raw -LiteralPath $lockPath | ConvertFrom-Json
    if ($lock.status -ne 'BATCH_A_PASSED' -or @($lock.batchIds).Count -ne 1) { throw 'Batch B is not authorised by the Batch A lock state.' }
    $pythonPhase = 'portfolio_b'
}

$temporaryPassword = 'LocalSynthetic-' + [guid]::NewGuid().ToString('N')
$env:MALL_LIVE_DEMO_PASSWORD = $temporaryPassword
$env:MALL_JAVA_BASE_URL = 'http://127.0.0.1:8085'
$env:MALL_DEMO_WEB_BASE_URL = 'http://127.0.0.1:5173'
$env:MALL_RUNTIME_PROVIDER_MODE = 'live'
$env:MALL_PROVIDER_LIVE_AUTH = '1'
$env:MALL_RELEASE_ID = $ReleaseId
$env:MALL_RELEASE_BATCH_ID = ''
$env:MALL_RELEASE_LEDGER_PATH = $ledgerPath
$env:MALL_RELEASE_LEDGER_HOST_PATH = $ledgerDirectory
$env:MALL_RELEASE_LEDGER_CONTAINER_PATH = '/app/release-ledger/ledger.jsonl'
$env:MALL_RUNTIME_COMMIT = $RuntimeCommit
$env:MALL_IMAGE_REVISION = $RuntimeCommit
$env:MALL_PROMPT_VERSION = 'agent_runtime_v3_3'

try {
    docker compose up -d --no-deps --force-recreate mall-ai-service | Out-Null
    Assert-ContainerIdentity
    $securePassword = ConvertTo-SecureString $temporaryPassword -AsPlainText -Force
    & (Join-Path $root 'scripts\Initialize-LocalDemoAccess.ps1') -DemoPassword $securePassword -PrepareCustomerFixtures | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Synthetic local demo fixture bootstrap failed.' }
    Push-Location (Join-Path $root 'mall-ai-service')
    try {
        & $python 'scripts\run_deepseek_release_batch.py' --phase $pythonPhase --release-id $ReleaseId --runtime-commit $RuntimeCommit --report $reportPath --lock $lockPath
        exit $LASTEXITCODE
    }
    finally { Pop-Location }
}
finally {
    Remove-Item Env:MALL_LIVE_DEMO_PASSWORD -ErrorAction SilentlyContinue
    Disable-LiveAuthorization
}

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$RuntimeCommit,
    [Parameter(Mandatory=$true)][ValidatePattern('^mall-v3\.0\.4-showcase-supplement-[a-z0-9._-]+$')][string]$ReleaseId
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if ((git branch --show-current).Trim() -ne 'codex/v3.0.4-eval-contract-alignment') { throw 'branch_mismatch' }
if (((git status --porcelain | Out-String).Trim()) -ne '') { throw 'worktree_not_clean' }
docker compose config --quiet
$healthy = @(docker compose -p mall-ai-demo ps --format '{{.Service}}|{{.State}}|{{.Health}}')
if ($healthy.Count -lt 8 -or @($healthy | Where-Object { $_ -notmatch '\|running\|healthy$' }).Count -gt 0) { throw 'compose_not_healthy' }

$ledgerDirectory = Join-Path $root "tmp\release-ledger-$ReleaseId"
$ledgerPath = Join-Path $ledgerDirectory 'ledger.jsonl'
$lockPath = Join-Path $root "docs\evidence\deepseek-showcase-supplement-lock-$ReleaseId.json"
$reportPath = Join-Path $root "tmp\v304-showcase-supplement-$ReleaseId\report.json"
if ((Test-Path -LiteralPath $ledgerDirectory) -or (Test-Path -LiteralPath $lockPath) -or (Test-Path -LiteralPath $reportPath)) { throw 'supplement_artifact_already_exists' }

$oldPassword = [Environment]::GetEnvironmentVariable('MALL_LIVE_DEMO_PASSWORD', 'Process')
if ([string]::IsNullOrWhiteSpace($oldPassword) -or $oldPassword.Length -lt 12) { throw 'missing_process_demo_password' }
try {
    [Environment]::SetEnvironmentVariable('MALL_RUNTIME_PROVIDER_MODE', 'live', 'Process')
    [Environment]::SetEnvironmentVariable('MALL_PROVIDER_LIVE_AUTH', '1', 'Process')
    [Environment]::SetEnvironmentVariable('MALL_RUNTIME_COMMIT', $RuntimeCommit, 'Process')
    [Environment]::SetEnvironmentVariable('MALL_IMAGE_REVISION', $RuntimeCommit, 'Process')
    [Environment]::SetEnvironmentVariable('MALL_RELEASE_ID', $ReleaseId, 'Process')
    [Environment]::SetEnvironmentVariable('MALL_RELEASE_LEDGER_HOST_PATH', $ledgerDirectory, 'Process')
    [Environment]::SetEnvironmentVariable('MALL_RELEASE_LEDGER_CONTAINER_PATH', '/app/release-ledger/ledger.jsonl', 'Process')
    [Environment]::SetEnvironmentVariable('MALL_RELEASE_LEDGER_PATH', $ledgerPath, 'Process')
    [Environment]::SetEnvironmentVariable('MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS', '40', 'Process')
    [Environment]::SetEnvironmentVariable('MALL_RELEASE_MAX_TOTAL_TOKENS', '100000', 'Process')
    [Environment]::SetEnvironmentVariable('MALL_RELEASE_RESERVE_TOKENS', '12000', 'Process')
    & .\mall-ai-service\.venv\Scripts\python.exe .\mall-ai-service\scripts\release_entry_contract.py --ledger-directory $ledgerDirectory --ledger-path $ledgerPath --lock-path $lockPath --container-ledger-path '/app/release-ledger/ledger.jsonl'
    if ($LASTEXITCODE -ne 0) { throw 'ledger_initialization_failed' }
    docker compose up -d --no-deps --force-recreate mall-ai-service | Out-Null
    $deadline = (Get-Date).AddSeconds(120)
    do { $version = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health/version' -TimeoutSec 5; if ($version.providerMode -eq 'live' -and $version.runtimeCommit -eq $RuntimeCommit -and $version.imageRevision -eq $RuntimeCommit) { break }; Start-Sleep -Seconds 2 } while ((Get-Date) -lt $deadline)
    if ($null -eq $version -or $version.providerMode -ne 'live' -or $version.runtimeCommit -ne $RuntimeCommit -or $version.imageRevision -ne $RuntimeCommit) { throw 'runtime_identity_mismatch' }
    docker compose exec -T mall-ai-service python -c "from pathlib import Path; p=Path('/app/release-ledger/ledger.jsonl'); assert p.exists() and p.stat().st_size == 0; f=p.open('r+b'); f.read(0); f.close()"
    if ($LASTEXITCODE -ne 0) { throw 'ledger_container_not_readwrite' }
    & .\mall-ai-service\.venv\Scripts\python.exe .\mall-ai-service\scripts\run_live_release_preflight.py
    if ($LASTEXITCODE -ne 0) { throw 'demo_account_preflight_failed' }
    & .\mall-ai-service\.venv\Scripts\python.exe .\mall-ai-service\scripts\run_showcase_supplement.py --release-id $ReleaseId --runtime-commit $RuntimeCommit --report $reportPath --lock $lockPath
    exit $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('MALL_RUNTIME_PROVIDER_MODE', 'deterministic', 'Process')
    [Environment]::SetEnvironmentVariable('MALL_PROVIDER_LIVE_AUTH', '0', 'Process')
    [Environment]::SetEnvironmentVariable('MALL_RUNTIME_COMMIT', $RuntimeCommit, 'Process')
    [Environment]::SetEnvironmentVariable('MALL_IMAGE_REVISION', $RuntimeCommit, 'Process')
    docker compose up -d --no-deps --force-recreate mall-ai-service | Out-Null
    Remove-Item Env:MALL_RUNTIME_PROVIDER_MODE,Env:MALL_PROVIDER_LIVE_AUTH,Env:MALL_RUNTIME_COMMIT,Env:MALL_IMAGE_REVISION,Env:MALL_RELEASE_ID,Env:MALL_RELEASE_LEDGER_HOST_PATH,Env:MALL_RELEASE_LEDGER_CONTAINER_PATH,Env:MALL_RELEASE_LEDGER_PATH,Env:MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS,Env:MALL_RELEASE_MAX_TOTAL_TOKENS,Env:MALL_RELEASE_RESERVE_TOKENS -ErrorAction SilentlyContinue
}

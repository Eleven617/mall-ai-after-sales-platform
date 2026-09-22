[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('Preflight','Final')][string]$Phase,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$RuntimeCommit,
    [Parameter(Mandatory=$true)][ValidatePattern('^mall-v3\.0\.4-[a-z0-9._-]+$')][string]$ReleaseId,
    [string]$ReplayReport = 'tmp/v304-contract-replay/replay.json',
    [string]$FieldReportDir = 'tmp/v304-field-acceptance-final',
    [string]$FieldReport = ''
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
$expectedBranch = 'codex/v3.0.4-eval-contract-alignment'
$branch = (git branch --show-current).Trim()
if ($branch -ne $expectedBranch) { throw "branch_mismatch:$branch" }
$head = (git rev-parse HEAD).Trim()
$status = (git status --porcelain | Out-String).Trim()
if ($status -ne '') { throw 'worktree_not_clean' }
git merge-base --is-ancestor $RuntimeCommit $head | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'runtime_commit_not_ancestor' }

docker info --format '{{.ServerVersion}}' | Out-Null
docker compose config --quiet
$healthy = @(docker compose -p mall-ai-demo ps --format '{{.Service}}|{{.State}}|{{.Health}}')
if ($healthy.Count -lt 8) { throw "compose_services_missing:$($healthy.Count)" }
if (@($healthy | Where-Object { $_ -notmatch '\|running\|healthy$' }).Count -gt 0) { throw 'compose_not_healthy' }

$version = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health/version' -TimeoutSec 10
if ($version.runtimeCommit -ne $RuntimeCommit -or $version.imageRevision -ne $RuntimeCommit) { throw 'runtime_identity_mismatch' }
if ($version.providerMode -notin @('deterministic','offline')) { throw 'provider_mode_not_offline' }

if ($Phase -eq 'Preflight') {
    & .\mall-ai-service\.venv\Scripts\python.exe .\mall-ai-service\scripts\run_v3_0_4_contract_replay.py --report $ReplayReport
    if ($LASTEXITCODE -ne 0) { throw 'contract_replay_failed' }
    $payload = Get-Content -Raw $ReplayReport | ConvertFrom-Json
    if ($payload.passed -ne 36 -or $payload.failed -ne 0 -or $payload.environmentBlocked -ne 0 -or $payload.providerCalls -ne 0 -or $payload.providerTokens -ne 0) { throw 'contract_replay_gate_failed' }
    if ([string]::IsNullOrWhiteSpace($FieldReport)) {
        throw 'field_report_required_for_preflight'
    }
    $field = Get-Content -Raw -LiteralPath $FieldReport | ConvertFrom-Json
    if ($field.testedCodeCommit -ne $RuntimeCommit -or $field.releaseGate.passed -ne $true -or $field.caseCount -ne 122) { throw 'field_acceptance_provenance_or_gate_failed' }
    if ($field.providerUsage.externalProviderRequests -ne 0 -or $field.providerUsage.externalProviderTokens -ne 0) { throw 'field_acceptance_provider_usage_nonzero' }
    Write-Output "V3_0_4_PREFLIGHT_PASSED runtime=$RuntimeCommit replay=36/36 phase=$Phase releaseId=$ReleaseId"
    exit 0
}

# The paid runner has its own fail-closed Python preflight before it creates a
# batch id, report, ledger entry, or lock.  This entry is the explicitly
# authorized single-batch path: it supplies a process-only synthetic password
# when the user scope has none, then delegates all release guards to Python.
# The password is never printed, persisted, or placed in a command argument.
function New-TemporaryDemoPassword {
    $bytes = New-Object byte[] 24
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        $rng.Dispose()
    }
    $encoded = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    return ('LocalSynthetic-' + $encoded)
}

function Get-BoundedReleaseLimit {
    param([string]$CurrentValue, [long]$Ceiling)
    $parsed = 0L
    if ([long]::TryParse($CurrentValue, [ref]$parsed) -and $parsed -gt 0 -and $parsed -lt $Ceiling) {
        return $parsed.ToString()
    }
    return $Ceiling.ToString()
}

$previousPassword = [Environment]::GetEnvironmentVariable('MALL_LIVE_DEMO_PASSWORD', 'Process')
$previousFixturePassword = [Environment]::GetEnvironmentVariable('MALL_FIELD_FIXTURE_PASSWORD', 'Process')
$previousMaxAttempts = [Environment]::GetEnvironmentVariable('MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS', 'Process')
$previousMaxTokens = [Environment]::GetEnvironmentVariable('MALL_RELEASE_MAX_TOTAL_TOKENS', 'Process')
$previousReserveTokens = [Environment]::GetEnvironmentVariable('MALL_RELEASE_RESERVE_TOKENS', 'Process')
$password = $previousPassword
if ([string]::IsNullOrWhiteSpace($password) -or $password.Trim().Length -lt 12) {
    $password = [Environment]::GetEnvironmentVariable('MALL_LIVE_DEMO_PASSWORD', 'User')
}
if ([string]::IsNullOrWhiteSpace($password) -or $password.Trim().Length -lt 12) {
    $password = New-TemporaryDemoPassword
}
[Environment]::SetEnvironmentVariable('MALL_LIVE_DEMO_PASSWORD', $password, 'Process')
[Environment]::SetEnvironmentVariable('MALL_FIELD_FIXTURE_PASSWORD', $password, 'Process')
[Environment]::SetEnvironmentVariable('MALL_JAVA_BASE_URL', 'http://127.0.0.1:8085', 'Process')
[Environment]::SetEnvironmentVariable('MALL_DEMO_WEB_BASE_URL', 'http://127.0.0.1:5173', 'Process')
[Environment]::SetEnvironmentVariable('MALL_RUNTIME_PROVIDER_MODE', 'live', 'Process')
[Environment]::SetEnvironmentVariable('MALL_PROVIDER_LIVE_AUTH', '1', 'Process')
[Environment]::SetEnvironmentVariable('MALL_RELEASE_ID', $ReleaseId, 'Process')
[Environment]::SetEnvironmentVariable('MALL_RELEASE_BATCH_ID', '', 'Process')
$ledgerDirectory = Join-Path $root "tmp\release-ledger-$ReleaseId"
$ledgerPath = Join-Path $ledgerDirectory 'ledger.jsonl'
$lockPath = Join-Path $root "docs\evidence\deepseek-release-lock-$ReleaseId.json"
$campaignPath = Join-Path $root 'docs\evidence\v304-live-retest-campaign.json'
[Environment]::SetEnvironmentVariable('MALL_RELEASE_LEDGER_HOST_PATH', $ledgerDirectory, 'Process')
[Environment]::SetEnvironmentVariable('MALL_RELEASE_LEDGER_CONTAINER_PATH', '/app/release-ledger/ledger.jsonl', 'Process')
[Environment]::SetEnvironmentVariable('MALL_RELEASE_LEDGER_PATH', $ledgerPath, 'Process')
[Environment]::SetEnvironmentVariable('MALL_RUNTIME_COMMIT', $RuntimeCommit, 'Process')
[Environment]::SetEnvironmentVariable('MALL_IMAGE_REVISION', $RuntimeCommit, 'Process')
[Environment]::SetEnvironmentVariable('MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS', (Get-BoundedReleaseLimit $previousMaxAttempts 80), 'Process')
[Environment]::SetEnvironmentVariable('MALL_RELEASE_MAX_TOTAL_TOKENS', (Get-BoundedReleaseLimit $previousMaxTokens 200000), 'Process')
[Environment]::SetEnvironmentVariable('MALL_RELEASE_RESERVE_TOKENS', '12000', 'Process')
$runnerExitCode = 1
try {
    Push-Location .\mall-ai-service
    try {
        & .\.venv\Scripts\python.exe -c "from app.config import settings; raise SystemExit(0 if settings.deepseek_api_key else 2)"
        if ($LASTEXITCODE -ne 0) { throw 'live_release_preflight_blocked:missing_provider_configuration' }
    } finally {
        Pop-Location
    }
    # Release-entry ownership: create exactly one new empty JSONL atomically.
    # Runtime reservation remains fail-closed when a mount or path is wrong.
    & .\mall-ai-service\.venv\Scripts\python.exe .\mall-ai-service\scripts\release_entry_contract.py `
        --ledger-directory $ledgerDirectory --ledger-path $ledgerPath --lock-path $lockPath `
        --container-ledger-path '/app/release-ledger/ledger.jsonl'
    if ($LASTEXITCODE -ne 0) { throw 'release_entry_preflight_blocked:ledger_initialization_failed' }
    $composeConfig = @(docker compose config)
    $composeConfigText = $composeConfig -join "`n"
    if ($LASTEXITCODE -ne 0 -or $composeConfigText -notmatch '/app/release-ledger') {
        throw 'release_entry_preflight_blocked:ledger_mount_missing'
    }
    # Recreate only the AI service so the same process-only authorization,
    # live mode, runtime identity, and host/container ledger path are present
    # in the service that the paid runner calls. Named data volumes remain
    # untouched.
    & docker compose up -d --no-deps --force-recreate mall-ai-service | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'live_release_preflight_blocked:runtime_recreate_failed' }
    $deadline = (Get-Date).AddSeconds(120)
    $liveVersion = $null
    do {
        try {
            $liveVersion = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health/version' -TimeoutSec 5
            if ($liveVersion.runtimeCommit -eq $RuntimeCommit -and $liveVersion.imageRevision -eq $RuntimeCommit -and $liveVersion.providerMode -eq 'live') { break }
        } catch { }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    if ($null -eq $liveVersion -or $liveVersion.runtimeCommit -ne $RuntimeCommit -or $liveVersion.imageRevision -ne $RuntimeCommit -or $liveVersion.providerMode -ne 'live') {
        throw 'live_release_preflight_blocked:runtime_identity_mismatch'
    }
    # Confirm the bind-mounted ledger is readable and writable from inside the
    # exact runtime container before any Batch/Lock/provider work begins.
    & docker compose exec -T mall-ai-service python -c "from pathlib import Path; p=Path('/app/release-ledger/ledger.jsonl'); f=p.open('r+b'); f.read(0); f.close(); assert p.stat().st_size == 0"
    if ($LASTEXITCODE -ne 0) { throw 'release_entry_preflight_blocked:ledger_container_not_readwrite' }
    & .\mall-ai-service\.venv\Scripts\python.exe .\mall-ai-service\scripts\run_live_release_preflight.py
    if ($LASTEXITCODE -ne 0) { throw 'live_release_preflight_blocked:demo_account_preflight_failed' }

    $reportPath = Join-Path $root "tmp\v304-minimal-retest-$ReleaseId\report.json"
    & .\mall-ai-service\.venv\Scripts\python.exe .\mall-ai-service\scripts\run_deepseek_release_batch.py `
        --phase minimal_retest --release-id $ReleaseId --runtime-commit $RuntimeCommit `
        --report $reportPath --lock $lockPath --campaign $campaignPath
    $runnerExitCode = $LASTEXITCODE
}
finally {
    if ($null -eq $previousPassword) { Remove-Item Env:MALL_LIVE_DEMO_PASSWORD -ErrorAction SilentlyContinue } else { [Environment]::SetEnvironmentVariable('MALL_LIVE_DEMO_PASSWORD', $previousPassword, 'Process') }
    if ($null -eq $previousFixturePassword) { Remove-Item Env:MALL_FIELD_FIXTURE_PASSWORD -ErrorAction SilentlyContinue } else { [Environment]::SetEnvironmentVariable('MALL_FIELD_FIXTURE_PASSWORD', $previousFixturePassword, 'Process') }
    if ($null -eq $previousMaxAttempts) { Remove-Item Env:MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS -ErrorAction SilentlyContinue } else { [Environment]::SetEnvironmentVariable('MALL_RELEASE_MAX_PROVIDER_HTTP_ATTEMPTS', $previousMaxAttempts, 'Process') }
    if ($null -eq $previousMaxTokens) { Remove-Item Env:MALL_RELEASE_MAX_TOTAL_TOKENS -ErrorAction SilentlyContinue } else { [Environment]::SetEnvironmentVariable('MALL_RELEASE_MAX_TOTAL_TOKENS', $previousMaxTokens, 'Process') }
    if ($null -eq $previousReserveTokens) { Remove-Item Env:MALL_RELEASE_RESERVE_TOKENS -ErrorAction SilentlyContinue } else { [Environment]::SetEnvironmentVariable('MALL_RELEASE_RESERVE_TOKENS', $previousReserveTokens, 'Process') }
    Remove-Item Env:MALL_JAVA_BASE_URL,Env:MALL_DEMO_WEB_BASE_URL,Env:MALL_RELEASE_ID,Env:MALL_RELEASE_BATCH_ID,Env:MALL_RELEASE_LEDGER_HOST_PATH,Env:MALL_RELEASE_LEDGER_CONTAINER_PATH,Env:MALL_RELEASE_LEDGER_PATH -ErrorAction SilentlyContinue
    $password = $null
    # Compose build args and container identity default to "unknown" when these
    # variables are absent. Restore the frozen deterministic runtime explicitly,
    # then verify it before removing the process-only values.
    [Environment]::SetEnvironmentVariable('MALL_RUNTIME_PROVIDER_MODE', 'deterministic', 'Process')
    [Environment]::SetEnvironmentVariable('MALL_PROVIDER_LIVE_AUTH', '0', 'Process')
    [Environment]::SetEnvironmentVariable('MALL_RUNTIME_COMMIT', $RuntimeCommit, 'Process')
    [Environment]::SetEnvironmentVariable('MALL_IMAGE_REVISION', $RuntimeCommit, 'Process')
    & docker compose up -d --no-deps --force-recreate mall-ai-service | Out-Null
    $restoreDeadline = (Get-Date).AddSeconds(120)
    $restoredVersion = $null
    do {
        try {
            $restoredVersion = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health/version' -TimeoutSec 5
            if ($restoredVersion.runtimeCommit -eq $RuntimeCommit -and $restoredVersion.imageRevision -eq $RuntimeCommit -and $restoredVersion.providerMode -eq 'deterministic') { break }
        } catch { }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $restoreDeadline)
    if ($null -eq $restoredVersion -or $restoredVersion.runtimeCommit -ne $RuntimeCommit -or $restoredVersion.imageRevision -ne $RuntimeCommit -or $restoredVersion.providerMode -ne 'deterministic') {
        Write-Error 'offline_runtime_restore_failed'
    }
    Remove-Item Env:MALL_RUNTIME_PROVIDER_MODE,Env:MALL_PROVIDER_LIVE_AUTH,Env:MALL_RUNTIME_COMMIT,Env:MALL_IMAGE_REVISION -ErrorAction SilentlyContinue
}
exit $runnerExitCode

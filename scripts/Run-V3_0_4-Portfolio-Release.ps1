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
if ((git status --porcelain) -ne '') { throw 'worktree_not_clean' }
if ((git merge-base --is-ancestor $RuntimeCommit $head); $LASTEXITCODE -ne 0) { throw 'runtime_commit_not_ancestor' }

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

# Final is intentionally guarded until a separately authorized online batch.
throw 'FINAL_ONLINE_BATCH_NOT_AUTHORIZED_IN_OFFLINE_ENTRY'

param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$FreezeCommit,
    [string]$Report = 'docs/evidence/v3.0.1-live-readiness.json'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'mall-ai-service\.venv\Scripts\python.exe'
$reportPath = Join-Path $root $Report
$checks = [ordered]@{}
$reasons = [System.Collections.Generic.List[string]]::new()

function Set-Check([string]$Name, [bool]$Value, [string]$Reason = '') {
    $checks[$Name] = $Value
    if (-not $Value -and $Reason) { $reasons.Add($Reason) }
}

function Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { return $null }
}

function RunQuiet([string]$File, [string[]]$Arguments) {
    & $File @Arguments *> $null
    return $LASTEXITCODE
}

$beforeStatus = (& git -C $root status --porcelain)
Set-Check 'git_worktree_clean_before_report' ($beforeStatus.Count -eq 0) 'Git 工作区在预检前不是 clean。'
Set-Check 'branch_correct' ((& git -C $root branch --show-current).Trim() -eq 'codex/v3.0.1-offline-acceptance') '分支不是 codex/v3.0.1-offline-acceptance。'
Set-Check 'head_is_freeze_commit' ((& git -C $root rev-parse HEAD).Trim() -eq $FreezeCommit) '当前 HEAD 与冻结 Commit 不一致。'
$changedAfterFreeze = @(& git -C $root diff --name-only $FreezeCommit HEAD)
Set-Check 'no_source_change_after_freeze' ($changedAfterFreeze.Count -eq 0) '冻结 Commit 之后存在变更。'
Set-Check 'python_runtime_exists' (Test-Path -LiteralPath $python -PathType Leaf) 'FastAPI 虚拟环境不存在。'

# The readiness entry owns the live container cutover.  These process-only
# variables never write a key or password to the repository.
$env:MALL_RUNTIME_PROVIDER_MODE = 'live'
$env:MALL_RUNTIME_COMMIT = $FreezeCommit
$env:MALL_IMAGE_REVISION = $FreezeCommit
$env:MALL_PROMPT_VERSION = 'agent_runtime_v3_3'
$env:MALL_SCHEMA_VERSION = 'task_runtime_v3_0'

$buildExit = RunQuiet 'docker' @('compose', 'build', 'mall-ai-service')
Set-Check 'live_image_build' ($buildExit -eq 0) 'mall-ai-service 镜像构建失败。'
$upExit = RunQuiet 'docker' @('compose', 'up', '-d', '--force-recreate', 'mall-ai-service')
Set-Check 'live_container_recreated' ($upExit -eq 0) 'mall-ai-service live 容器重建失败。'

$healthy = $false
for ($attempt = 0; $attempt -lt 36; $attempt++) {
    $rows = @(docker compose ps --format '{{.Service}}|{{.State}}|{{.Health}}' 2>$null)
    if ($rows -contains 'mall-ai-service|running|healthy') { $healthy = $true; break }
    Start-Sleep -Seconds 5
}
Set-Check 'docker_stack_ai_healthy' $healthy 'mall-ai-service 未达到 healthy。'

$containerId = (& docker compose ps -q mall-ai-service 2>$null).Trim()
$container = $null
$image = $null
if ($containerId) {
    try {
        $container = (@(docker inspect $containerId | ConvertFrom-Json))[0]
        if ($container.Image) { $image = (@(docker inspect $container.Image | ConvertFrom-Json))[0] }
    } catch { $container = $null; $image = $null }
}
$containerEnv = @()
$containerLabels = @{}
$imageLabels = @{}
if ($container) {
    $containerEnv = @($container.Config.Env)
    if ($container.Config.Labels) { $containerLabels = $container.Config.Labels }
}
if ($image -and $image.Config.Labels) { $imageLabels = $image.Config.Labels }
$keyEntry = @($containerEnv | Where-Object { $_ -like 'DEEPSEEK_API_KEY=*' } | Select-Object -First 1)
$keyConfigured = $keyEntry.Count -eq 1 -and $keyEntry[0].Length -gt 'DEEPSEEK_API_KEY='.Length
Set-Check 'deepseek_key_configured' $keyConfigured '容器没有配置 DeepSeek Key；未打印或读取 Key 内容。'
Set-Check 'container_label_revision' ($containerLabels['org.opencontainers.image.revision'] -eq $FreezeCommit) '容器 label revision 与冻结 Commit 不一致。'
Set-Check 'image_label_revision' ($imageLabels['org.opencontainers.image.revision'] -eq $FreezeCommit) '镜像 label revision 与冻结 Commit 不一致。'
Set-Check 'container_runtime_commit' (@($containerEnv | Where-Object { $_ -eq "MALL_RUNTIME_COMMIT=$FreezeCommit" }).Count -eq 1) '容器运行时 Commit 不一致。'
Set-Check 'container_provider_mode_live' (@($containerEnv | Where-Object { $_ -eq 'MALL_RUNTIME_PROVIDER_MODE=live' }).Count -eq 1) '容器 Provider mode 不是 live。'

$version = $null
try { $version = Invoke-RestMethod -UseBasicParsing -Uri 'http://127.0.0.1:8000/health/version' -TimeoutSec 8 } catch { $version = $null }
$versionOk = $null -ne $version -and $version.runtimeCommit -eq $FreezeCommit -and $version.imageRevision -eq $FreezeCommit -and $version.providerMode -eq 'live' -and $version.model -eq 'deepseek-flash' -and $version.thinkingMode -eq 'enabled' -and $version.reasoningEffort -eq 'high' -and $version.promptVersion -eq 'agent_runtime_v3_3' -and $version.skillCatalogVersion -eq 'skill_catalog_v3_0'
Set-Check 'runtime_identity_endpoint' $versionOk '运行时身份端点未同时证明 Commit、镜像 revision、live、模型和版本。'

$ledgerMountOk = $false
if ($container) {
    $expectedLedger = [IO.Path]::GetFullPath((Join-Path $root 'tmp\release-ledger')).TrimEnd('\')
    foreach ($mount in @($container.Mounts)) {
        if ($mount.Destination -eq '/app/release-ledger') {
            $actual = [IO.Path]::GetFullPath([string]$mount.Source).TrimEnd('\')
            $ledgerMountOk = $mount.Type -eq 'bind' -and $actual.Equals($expectedLedger, [StringComparison]::OrdinalIgnoreCase)
        }
    }
}
Set-Check 'ledger_host_container_mapping' $ledgerMountOk '主机 tmp/release-ledger 未映射到容器 /app/release-ledger。'

$deterministic = JsonFile (Join-Path $root 'tmp\offline-field\showcase-deterministic.json')
$replay = JsonFile (Join-Path $root 'tmp\offline-field\showcase-replay.json')
function ShowcaseReady($Report) {
    if ($null -eq $Report -or $Report.status -ne 'passed' -or $Report.browserFrameCount -lt 12) { return $false }
    $groups = @($Report.frameGroups.PSObject.Properties)
    if ($groups.Count -ne 3) { return $false }
    foreach ($property in $groups) {
        if (-not $property.Value.valid -or $property.Value.frameCount -lt 4 -or $property.Value.adjacentDistinct -ne $true) { return $false }
        foreach ($frame in @($property.Value.frames)) {
            if (-not (Test-Path -LiteralPath (Join-Path $root ([string]$frame)) -PathType Leaf)) { return $false }
        }
    }
    return @($Report.gifPaths).Count -eq 3 -and (@($Report.gifPaths) | ForEach-Object { (Get-Item (Join-Path $root ([string]$_))).Length -le 3MB } | Where-Object { -not $_ }).Count -eq 0
}
Set-Check 'deterministic_showcase_frames' (ShowcaseReady $deterministic) 'deterministic 展示链没有三条链各 4 张有效帧和 3 个离线 GIF。'
Set-Check 'replay_showcase_frames' (ShowcaseReady $replay) 'replay 展示链没有三条链各 4 张有效帧和 3 个离线 GIF。'

$fieldPath = Get-ChildItem -LiteralPath (Join-Path $root 'tmp\offline-field-acceptance') -Filter 'field-acceptance.json' -Recurse -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$field = if ($fieldPath) { JsonFile $fieldPath.FullName } else { $null }
$fieldReady = $null -ne $field -and $field.releaseGate.passed -eq $true -and $field.caseCount -eq 122 -and (@($field.categories.PSObject.Properties) | Where-Object { $_.Value.passed -ne $_.Value.expected -or $_.Value.failed -ne 0 -or $_.Value.environmentBlocked -ne 0 }).Count -eq 0 -and $field.testedCodeCommit -eq $FreezeCommit
Set-Check 'field_acceptance_122_current' $fieldReady '现场 122 条报告不存在、未全通过或不是冻结 Commit。'

$manifestExit = RunQuiet $python @('scripts\validate_v3_release_manifest.py')
$preflightExit = RunQuiet $python @('scripts\run_v3_release_preflight.py')
Set-Check 'manifest_validation' ($manifestExit -eq 0) 'v3 release manifest validation 失败。'
Set-Check 'deterministic_preflight' ($preflightExit -eq 0) 'v3 deterministic preflight 失败。'
$manifestHash = Sha256 (Join-Path $root 'evals\v3\release-manifest.json')
$mainHash = Sha256 (Join-Path $root 'mall-ai-service\evals\live_model_synthetic_cases.v1.json')
$supplementalHash = Sha256 (Join-Path $root 'mall-ai-service\evals\live_model_agent_holdout_cases.v1.json')
$groundingHash = Sha256 (Join-Path $root 'mall-ai-service\evals\rag2_golden_cases.v1.json')
Set-Check 'evaluation_hashes_present' ($manifestHash -and $mainHash -and $supplementalHash -and $groundingHash) '版本化评测集缺失。'

$releaseId = "v3.0.1-final-$FreezeCommit"
$lockPath = Join-Path $root "docs\evidence\deepseek-release-lock-v3.0.1-final-$FreezeCommit.json"
Set-Check 'new_release_id_unused' (-not (Test-Path -LiteralPath $lockPath)) '新的 Release ID 或锁路径已经存在。'
$ledgerEvents = @()
if (Test-Path -LiteralPath (Join-Path $root 'tmp\release-ledger\ledger.jsonl')) {
    foreach ($line in Get-Content -LiteralPath (Join-Path $root 'tmp\release-ledger\ledger.jsonl')) {
        try { $event = $line | ConvertFrom-Json; if ($event) { $ledgerEvents += $event } } catch { }
    }
}
$providerBefore = @($ledgerEvents | Where-Object { $_.eventType -eq 'provider_request' }).Count
Set-Check 'provider_requests_before_live_zero' ($providerBefore -eq 0) "正式批次前账本已有 $providerBefore 个 Provider 事件。"

$oldLocks = [ordered]@{}
foreach ($old in @('docs\evidence\deepseek-release-lock.json', 'docs\evidence\deepseek-release-lock-v3.0.1.json')) {
    $oldPath = Join-Path $root $old
    $oldLocks[$old.Replace('\','/')] = Sha256 $oldPath
}

$ready = ($reasons.Count -eq 0) -and (@($checks.Values | Where-Object { -not $_ }).Count -eq 0)
$payload = [ordered]@{
    schemaVersion = 'mall-v3.0.1-live-readiness.v1'
    generatedAt = (Get-Date).ToUniversalTime().ToString('o')
    freezeCommit = $FreezeCommit
    branch = (& git -C $root branch --show-current).Trim()
    offlineAcceptanceComplete = $ready
    liveRunReady = $ready
    providerRequestsBeforeLive = $providerBefore
    releaseId = $releaseId
    releaseLock = $lockPath.Substring($root.Length + 1).Replace('\','/')
    checks = $checks
    reasons = @($reasons)
    runtimeIdentity = $version
    datasetHashes = [ordered]@{ manifest = $manifestHash; main = $mainHash; supplemental = $supplementalHash; grounding = $groundingHash }
    oldLockSha256 = $oldLocks
    fieldReport = if ($fieldPath) { $fieldPath.FullName.Substring($root.Length + 1).Replace('\','/') } else { $null }
}
$reportDir = Split-Path -Parent $reportPath
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$payload | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $reportPath -Encoding UTF8

if ($ready) {
    Write-Output 'OFFLINE_ACCEPTANCE_COMPLETE=true'
    Write-Output 'LIVE_RUN_READY=true'
    Write-Output 'PROVIDER_REQUESTS_BEFORE_LIVE=0'
    exit 0
}
Write-Output 'OFFLINE_ACCEPTANCE_COMPLETE=false'
Write-Output 'LIVE_RUN_READY=false'
Write-Output ("READINESS_FAILURES=" + (@($reasons) -join ';'))
exit 1

param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$FreezeCommit,
    [string]$Report = 'docs/evidence/v3.0.2-live-readiness.json',
    [string]$SlowReport = 'tmp/v3.0.2-slow-gateway.json',
    [string]$FieldReport = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'mall-ai-service\.venv\Scripts\python.exe'
$reportPath = Join-Path $root $Report
$slowPath = Join-Path $root $SlowReport
$ledgerDirectory = Join-Path $root 'tmp\release-ledger-v3.0.2'
$ledgerPath = Join-Path $ledgerDirectory 'ledger.jsonl'
$checks = [ordered]@{}
$reasons = [System.Collections.Generic.List[string]]::new()

function Set-Check([string]$Name, [bool]$Value, [string]$Reason = '') {
    $checks[$Name] = $Value
    if (-not $Value -and $Reason) { $reasons.Add($Reason) }
}
function JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { return $null }
}
function Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function RunQuiet([string]$File, [string[]]$Arguments) {
    & $File @Arguments *> $null
    return $LASTEXITCODE
}

$beforeStatus = @(& git -C $root status --porcelain)
Set-Check 'git_worktree_clean_before_report' ($beforeStatus.Count -eq 0) '预检前工作区不是 clean。'
Set-Check 'branch_correct' ((& git -C $root branch --show-current).Trim() -eq 'codex/v3.0.2-offline-candidate') '当前分支不是 v3.0.2 独立候选分支。'
$currentHead = (& git -C $root rev-parse HEAD).Trim()
$freezeAncestor = & git -C $root merge-base --is-ancestor $FreezeCommit $currentHead 2>$null
Set-Check 'freeze_commit_is_ancestor' ($freezeAncestor -eq 0) '冻结 Commit 不是当前证据提交的祖先。'
$postFreezePaths = @(& git -C $root diff --name-only "$FreezeCommit..$currentHead")
$runtimePrefixes = @('mall-ai-service/app/', 'mall2/', 'mall-ai-web/src/', 'evals/', 'mall2/document/sql/migrations/', 'docker-compose.yml', 'mall-ai-web/nginx.conf')
$runtimeChangedAfterFreeze = @($postFreezePaths | Where-Object { $path = $_; $runtimePrefixes | Where-Object { $path.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) } })
Set-Check 'no_runtime_change_after_freeze' ($runtimeChangedAfterFreeze.Count -eq 0) ('冻结后出现运行时代码变更：' + ($runtimeChangedAfterFreeze -join ', '))
Set-Check 'python_runtime_exists' (Test-Path -LiteralPath $python -PathType Leaf) 'FastAPI 虚拟环境不存在。'
New-Item -ItemType Directory -Force -Path $ledgerDirectory | Out-Null

$env:MALL_RELEASE_LEDGER_HOST_PATH = './tmp/release-ledger-v3.0.2'
$env:MALL_RELEASE_LEDGER_PATH = $ledgerPath
$env:MALL_RUNTIME_PROVIDER_MODE = 'live'
$env:MALL_RUNTIME_COMMIT = $FreezeCommit
$env:MALL_IMAGE_REVISION = $FreezeCommit
$env:MALL_PROMPT_VERSION = 'agent_runtime_v3_3'
$env:MALL_SCHEMA_VERSION = 'task_runtime_v3_0'
$env:MALL_DETERMINISTIC_PROVIDER_DELAY_SECONDS = '0'
$buildExit = RunQuiet 'docker' @('compose', 'build', 'mall-ai-service', 'mall-ai-web')
Set-Check 'live_image_build' ($buildExit -eq 0) 'v3.0.2 镜像构建失败。'
$upExit = RunQuiet 'docker' @('compose', 'up', '-d', '--force-recreate', 'mall-ai-service', 'mall-ai-web')
Set-Check 'live_container_recreated' ($upExit -eq 0) 'v3.0.2 容器重建失败。'

$healthy = $false
for ($attempt = 0; $attempt -lt 36; $attempt++) {
    $rows = @(docker compose ps --format '{{.Service}}|{{.State}}|{{.Health}}' 2>$null)
    if ($rows -contains 'mall-ai-service|running|healthy' -and $rows -contains 'mall-ai-web|running|healthy') { $healthy = $true; break }
    Start-Sleep -Seconds 5
}
Set-Check 'docker_stack_ai_web_healthy' $healthy 'mall-ai-service 或 mall-ai-web 未 healthy。'

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
Set-Check 'deepseek_key_configured' ($keyEntry.Count -eq 1 -and $keyEntry[0].Length -gt 'DEEPSEEK_API_KEY='.Length) '未配置 DeepSeek Key；只检查存在性，不输出内容。'
$containerRevision = if ($containerLabels.PSObject.Properties['org.opencontainers.image.revision']) { $containerLabels.PSObject.Properties['org.opencontainers.image.revision'].Value } else { $null }
$imageRevision = if ($imageLabels.PSObject.Properties['org.opencontainers.image.revision']) { $imageLabels.PSObject.Properties['org.opencontainers.image.revision'].Value } else { $null }
Set-Check 'container_image_identity' ($containerRevision -eq $FreezeCommit -and $imageRevision -eq $FreezeCommit) '容器/镜像 revision 与冻结 Commit 不一致。'
$version = $null
try { $version = Invoke-RestMethod -UseBasicParsing -Uri 'http://127.0.0.1:8000/health/version' -TimeoutSec 8 } catch { $version = $null }
Set-Check 'runtime_identity_live' ($null -ne $version -and $version.runtimeCommit -eq $FreezeCommit -and $version.imageRevision -eq $FreezeCommit -and $version.providerMode -eq 'live' -and $version.model -eq 'deepseek-flash' -and $version.thinkingMode -eq 'enabled' -and $version.reasoningEffort -eq 'high' -and $version.promptVersion -eq 'agent_runtime_v3_3' -and $version.skillCatalogVersion -eq 'skill_catalog_v3_0') '运行时身份不符合 v3.0.2 live-ready 合同。'

$mountOk = $false
if ($container) {
    $expected = [IO.Path]::GetFullPath($ledgerDirectory).TrimEnd('\')
    foreach ($mount in @($container.Mounts)) {
        if ($mount.Destination -eq '/app/release-ledger') {
            $actual = [IO.Path]::GetFullPath([string]$mount.Source).TrimEnd('\')
            $mountOk = $mount.Type -eq 'bind' -and $actual.Equals($expected, [StringComparison]::OrdinalIgnoreCase)
        }
    }
}
Set-Check 'ledger_host_container_mapping' $mountOk 'v3.0.2 主机与容器 ledger 未指向同一物理目录。'

$slow = JsonFile $slowPath
$slowReady = $null -ne $slow -and $slow.status -eq 'passed' -and $slow.throughProxy -eq $true -and $slow.httpStatus -eq 201 -and $slow.taskStatus -eq 'ready_to_commit' -and $slow.durationAtLeast65Seconds -eq $true -and $slow.runtimeWithin240Seconds -eq $true -and $slow.javaWriteObserved -eq $false -and $slow.externalProviderRequests -eq 0
Set-Check 'slow_gateway_test_passed' $slowReady '慢调用现场未通过、未走 Nginx、未达到 65 秒、超过 Runtime 上限、或产生了写入/Provider 请求。'

$events = @()
if (Test-Path -LiteralPath $ledgerPath -PathType Leaf) {
    foreach ($line in Get-Content -LiteralPath $ledgerPath) { try { $event = $line | ConvertFrom-Json; if ($event) { $events += $event } } catch {} }
}
$providerEvents = @($events | Where-Object { $_.eventType -eq 'provider_request' })
$slowBatch = if ($slow) { [string]$slow.batchId } else { '' }
$slowEvents = @($events | Where-Object { $_.batchId -eq $slowBatch })
$slowLedger = if ($slow -and $slow.ledger) { $slow.ledger } else { $null }
$ledgerOk = $null -ne $slowLedger -and $slowLedger.providerRequests -eq $providerEvents.Count -and $slowLedger.providerTokens -eq (($providerEvents | Measure-Object -Property totalTokens -Sum).Sum) -and $slowLedger.events -eq $slowEvents.Count -and $providerEvents.Count -eq 0
Set-Check 'ledger_reconciliation_passed' $ledgerOk 'v3.0.2 报告、锁/原始 ledger 对账不一致或存在 Provider 事件。'
Set-Check 'external_provider_requests_zero' ($providerEvents.Count -eq 0) '离线候选阶段观察到外部 Provider 请求。'

$manifestExit = RunQuiet $python @('scripts\validate_v3_release_manifest.py')
$preflightExit = RunQuiet $python @('scripts\run_v3_release_preflight.py')
Set-Check 'manifest_and_preflight' ($manifestExit -eq 0 -and $preflightExit -eq 0) 'manifest/preflight 未通过。'

$field = $null
$fieldPath = $null
if ($FieldReport) {
    $fieldPath = Join-Path $root $FieldReport
    $field = JsonFile $fieldPath
}
if ($null -eq $field) {
    $fieldPath = Get-ChildItem -LiteralPath (Join-Path $root 'tmp\offline-field-acceptance') -Filter 'field-acceptance.json' -Recurse -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($fieldPath) { $field = JsonFile $fieldPath.FullName }
}
$fieldReady = $null -ne $field -and $field.releaseGate.passed -eq $true -and $field.caseCount -eq 122 -and $field.testedCodeCommit -eq $FreezeCommit -and (@($field.categories.PSObject.Properties) | Where-Object { $_.Value.passed -ne $_.Value.expected -or $_.Value.failed -ne 0 -or $_.Value.environmentBlocked -ne 0 }).Count -eq 0
Set-Check 'field_acceptance_122_current' $fieldReady '122 条现场报告缺失、非当前冻结 Commit 或存在失败/阻塞。'
$fieldReportRelative = $null
if ($fieldPath) {
    $fieldReportFullPath = if ($fieldPath -is [System.IO.FileInfo]) { $fieldPath.FullName } else { [string]$fieldPath }
    $fieldReportRelative = $fieldReportFullPath.Substring($root.Length + 1).Replace('\','/')
}

$fastapiReport = Join-Path $root 'tmp\v3.0.2\fastapi-report.json'
$fastapiJunit = Join-Path $root 'tmp\v3.0.2\fastapi-junit.xml'
$env:MALL_FASTAPI_REPORT = $fastapiReport
$env:MALL_FASTAPI_JUNIT = $fastapiJunit
$validatorExit = RunQuiet 'python' @('scripts\validate_public_release.py')
Set-Check 'ci_validator_dynamic' ($validatorExit -eq 0) '公共校验器未读取当前机器报告或动态事实校验失败。'

$ready = ($reasons.Count -eq 0) -and (@($checks.Values | Where-Object { -not $_ }).Count -eq 0)
$payload = [ordered]@{
    schemaVersion = 'mall-v3.0.2-live-readiness.v1'
    generatedAt = (Get-Date).ToUniversalTime().ToString('o')
    freezeCommit = $FreezeCommit
    branch = (& git -C $root branch --show-current).Trim()
    OFFLINE_ACCEPTANCE_COMPLETE = $ready
    SLOW_GATEWAY_TEST_PASSED = [bool]$checks['slow_gateway_test_passed']
    LEDGER_RECONCILIATION_PASSED = [bool]$checks['ledger_reconciliation_passed']
    CI_VALIDATOR_DYNAMIC = [bool]$checks['ci_validator_dynamic']
    EXTERNAL_PROVIDER_REQUESTS = $providerEvents.Count
    V3_0_2_LIVE_READY = $ready
    checks = $checks
    reasons = @($reasons)
    runtimeIdentity = $version
    slowReport = if (Test-Path -LiteralPath $slowPath) { $slowPath.Substring($root.Length + 1).Replace('\','/') } else { $null }
    slowReportSha256 = Sha256 $slowPath
    ledgerPath = if (Test-Path -LiteralPath $ledgerPath) { $ledgerPath.Substring($root.Length + 1).Replace('\','/') } else { $null }
    ledgerSha256 = Sha256 $ledgerPath
    fieldReport = $fieldReportRelative
    oldLockSha256 = [ordered]@{
        'docs/evidence/deepseek-release-lock.json' = Sha256 (Join-Path $root 'docs\evidence\deepseek-release-lock.json')
        'docs/evidence/deepseek-release-lock-v3.0.1.json' = Sha256 (Join-Path $root 'docs\evidence\deepseek-release-lock-v3.0.1.json')
        'docs/evidence/deepseek-release-lock-v3.0.1-final-06ef600e51e7b0dc362d43a98e274c28144738d8.json' = Sha256 (Join-Path $root 'docs\evidence\deepseek-release-lock-v3.0.1-final-06ef600e51e7b0dc362d43a98e274c28144738d8.json')
    }
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $reportPath) | Out-Null
$payload | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath $reportPath -Encoding UTF8

Remove-Item Env:MALL_FASTAPI_REPORT -ErrorAction SilentlyContinue
Remove-Item Env:MALL_FASTAPI_JUNIT -ErrorAction SilentlyContinue
Remove-Item Env:MALL_RELEASE_LEDGER_HOST_PATH -ErrorAction SilentlyContinue
Remove-Item Env:MALL_RELEASE_LEDGER_PATH -ErrorAction SilentlyContinue
Remove-Item Env:MALL_RUNTIME_PROVIDER_MODE -ErrorAction SilentlyContinue
Remove-Item Env:MALL_RUNTIME_COMMIT -ErrorAction SilentlyContinue
Remove-Item Env:MALL_IMAGE_REVISION -ErrorAction SilentlyContinue
Remove-Item Env:MALL_PROMPT_VERSION -ErrorAction SilentlyContinue
Remove-Item Env:MALL_SCHEMA_VERSION -ErrorAction SilentlyContinue
Remove-Item Env:MALL_DETERMINISTIC_PROVIDER_DELAY_SECONDS -ErrorAction SilentlyContinue

if ($ready) {
    Write-Output 'OFFLINE_ACCEPTANCE_COMPLETE=true'
    Write-Output 'SLOW_GATEWAY_TEST_PASSED=true'
    Write-Output 'LEDGER_RECONCILIATION_PASSED=true'
    Write-Output 'CI_VALIDATOR_DYNAMIC=true'
    Write-Output 'EXTERNAL_PROVIDER_REQUESTS=0'
    Write-Output 'V3_0_2_LIVE_READY=true'
    exit 0
}
Write-Output 'V3_0_2_LIVE_READY=false'
Write-Output ('READINESS_FAILURES=' + (@($reasons) -join ';'))
exit 1

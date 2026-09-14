param(
    [string]$ReleaseId = '',
    [string]$Report = '',
    [string]$RuntimeCommit = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'mall-ai-service\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'mall-ai-service/.venv is missing.'
}
${resolvedRuntimeCommit} = $true
if ([string]::IsNullOrWhiteSpace($RuntimeCommit)) {
    ${resolvedRuntimeCommit} = $false
    $RuntimeCommit = (& git -C $root rev-parse HEAD).Trim()
}
$runtimeCommit = $RuntimeCommit.Trim()
if ((-not ${resolvedRuntimeCommit} -and $LASTEXITCODE -ne 0) -or $runtimeCommit -notmatch '^[0-9a-f]{40}$') {
    throw 'Cannot resolve the runtime commit.'
}
if ([string]::IsNullOrWhiteSpace($ReleaseId)) {
    $ReleaseId = 'v3.0-deepseek-flash-' + $runtimeCommit.Substring(0, 12)
}
if ([string]::IsNullOrWhiteSpace($Report)) {
    $Report = Join-Path $root 'tmp\deepseek-batch-1-showcase.json'
}
$arguments = @(
    (Join-Path $root 'mall-ai-service\scripts\run_deepseek_release_batch.py'),
    '--phase', 'showcase',
    '--release-id', $ReleaseId,
    '--runtime-commit', $runtimeCommit,
    '--report', $Report
)
& $python @arguments
exit $LASTEXITCODE

param(
    [string]$ReleaseId = '',
    [string]$Report = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'mall-ai-service\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'mall-ai-service/.venv is missing.'
}
$runtimeCommit = (& git -C $root rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $runtimeCommit -notmatch '^[0-9a-f]{40}$') {
    throw 'Cannot resolve the runtime commit.'
}
if ([string]::IsNullOrWhiteSpace($ReleaseId)) {
    $ReleaseId = 'v3.0-deepseek-flash-' + $runtimeCommit.Substring(0, 12)
}
if ([string]::IsNullOrWhiteSpace($Report)) {
    $Report = Join-Path $root 'tmp\deepseek-batch-2-final.json'
}
$arguments = @(
    (Join-Path $root 'mall-ai-service\scripts\run_deepseek_release_batch.py'),
    '--phase', 'final',
    '--release-id', $ReleaseId,
    '--runtime-commit', $runtimeCommit,
    '--report', $Report
)
& $python @arguments
exit $LASTEXITCODE

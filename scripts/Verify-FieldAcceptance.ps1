[CmdletBinding()]
param(
    [string]$Manifest = "evals/v3/release-manifest.json",
    [string]$ReportDir = "tmp/field-acceptance",
    [string]$Fixture,
    [string]$Password,
    [string[]]$Categories = @("browser_e2e", "java_mysql_integration", "fault_injection", "durable_async_recovery"),
    [string]$FaultComposeProject,
    [string]$FaultComposeOverride
)

$python = Join-Path $PSScriptRoot "..\mall-ai-service\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Expected the project virtualenv at $python"
}

$args = @(
    "mall-ai-service/scripts/verify_field_acceptance.py",
    "--manifest", $Manifest,
    "--report-dir", $ReportDir,
    "--categories"
) + $Categories
if ($Fixture) { $args += @("--fixture", $Fixture) }
if ($Password) { $args += @("--password", $Password) }
if ($FaultComposeProject) { $args += @("--fault-compose-project", $FaultComposeProject) }
if ($FaultComposeOverride) { $args += @("--fault-compose-override", $FaultComposeOverride) }

& $python @args
exit $LASTEXITCODE

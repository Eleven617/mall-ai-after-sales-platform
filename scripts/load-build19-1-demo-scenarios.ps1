[CmdletBinding()]
param(
  [switch]$Confirm
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repoRoot 'docker-compose.yml'
$scenarioFile = Join-Path $repoRoot 'mall2\document\sql\demo\build19_1_rich_scenarios.sql'

if (-not $Confirm) {
  throw 'This script only adds the explicit local Build 19.1 demo records. Re-run with -Confirm after reviewing the SQL file.'
}
if (-not (Test-Path -LiteralPath $composeFile) -or -not (Test-Path -LiteralPath $scenarioFile)) {
  throw 'The workspace layout is incomplete; expected docker-compose.yml and the Build 19.1 scenario SQL file.'
}

Get-Content -LiteralPath $scenarioFile -Raw |
  docker compose -f $composeFile exec -T mysql sh -ec 'exec mysql --protocol=socket --user=root --password="$MYSQL_ROOT_PASSWORD" --default-character-set=utf8 mall'

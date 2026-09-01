[CmdletBinding()]
param(
    [switch]$RemoveDemoData
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $projectRoot "docker-compose.yml"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop was not found."
}

if ($RemoveDemoData) {
    $confirmation = Read-Host "This deletes Compose-managed local MySQL, Redis, MongoDB, and RabbitMQ demo data. Type DELETE_DEMO_DATA to continue"
    if ($confirmation -ne "DELETE_DEMO_DATA") {
        Write-Host "Cancelled. No data was removed."
        return
    }
    & docker compose -f $composeFile down --volumes
} else {
    & docker compose -f $composeFile down
}

if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose failed to stop."
}

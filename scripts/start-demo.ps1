[CmdletBinding()]
param(
    [switch]$PrepareDemoData,
    [switch]$SkipBuild,
    [switch]$SkipRagBootstrap,
    [int]$TimeoutSeconds = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $projectRoot "docker-compose.yml"
$aiProject = Join-Path $projectRoot "mall-ai-service"
$python = Join-Path $aiProject ".venv\Scripts\python.exe"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop was not found. Install and start Docker Desktop first."
}
if (-not (Test-Path (Join-Path $aiProject ".env"))) {
    throw "mall-ai-service/.env is missing. Copy .env.example and set model keys."
}
if (-not (Test-Path $python)) {
    throw "Python virtual environment was not found: $python"
}

if (-not $SkipRagBootstrap) {
    $ragBootstrap = Join-Path $aiProject "scripts\prepare_local_rag.py"
    if (-not (Test-Path -LiteralPath $ragBootstrap)) {
        throw "Local RAG bootstrap script was not found: $ragBootstrap"
    }

    & $python $ragBootstrap --check-only
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Preparing the local embedding model and policy index for this clone..."
        & $python $ragBootstrap
        if ($LASTEXITCODE -ne 0) {
            throw "Local RAG preparation failed. Check normal network access for the first embedding-model download and retry."
        }
    } else {
        Write-Host "Local RAG artifacts are ready."
    }
}

function Ensure-LocalBaseImage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Image
    )

    & docker image inspect $Image *> $null
    if ($LASTEXITCODE -eq 0) {
        return
    }

    Write-Host "Pulling required base image: $Image"
    & docker pull $Image
    if ($LASTEXITCODE -ne 0) {
        throw "Docker could not pull required base image: $Image"
    }
}

if (-not $SkipBuild) {
    # Resolve base images through the Docker engine before BuildKit runs. This
    # avoids a separate BuildKit proxy path on Windows Docker Desktop while
    # still using pinned images and the normal local image cache.
    $baseImages = @(
        "mysql:5.7.44",
        "redis:7.2-alpine",
        "mongo:4.4",
        "rabbitmq:3.13-management-alpine",
        "python:3.12-slim",
        "maven:3.9.9-eclipse-temurin-8",
        "eclipse-temurin:8-jre-jammy",
        "node:22-alpine",
        "nginx:1.27-alpine"
    )
    foreach ($image in $baseImages) {
        Ensure-LocalBaseImage -Image $image
    }

    & docker compose -f $composeFile build --pull=false
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed to build the demo images. Run docker compose -f $composeFile logs."
    }
}

& docker compose -f $composeFile up -d --no-build
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose failed to start. Run docker compose -f $composeFile logs."
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$stackCheck = Join-Path $aiProject "scripts\verify_compose_stack.py"
do {
    & $python $stackCheck
    if ($LASTEXITCODE -eq 0) {
        break
    }
    Start-Sleep -Seconds 3
} while ((Get-Date) -lt $deadline)

if ($LASTEXITCODE -ne 0) {
    throw "Services did not become ready within $TimeoutSeconds seconds. Check Docker Compose logs."
}

Write-Host "Services are ready:"
Write-Host "  Browser demo: http://127.0.0.1:5173"
Write-Host "  FastAPI docs: http://127.0.0.1:8000/docs"
Write-Host "  Java health: http://127.0.0.1:8085/actuator/health"

if (-not $PrepareDemoData) {
    return
}

$securePassword = Read-Host "Password for disposable local demo accounts" -AsSecureString
$demoPassword = [System.Net.NetworkCredential]::new("", $securePassword).Password
if ([string]::IsNullOrWhiteSpace($demoPassword)) {
    throw "The demo-account password cannot be empty."
}

$temporaryNames = @(
    "MALL_LIVE_DEMO_PASSWORD",
    "MALL_JAVA_BASE_URL",
    "MALL_LIVE_DEMO_RESULT_FILE",
    "MALL_TEST_USER_A",
    "MALL_TEST_PASSWORD_A",
    "MALL_TEST_ORDER_A",
    "MALL_TEST_USER_B",
    "MALL_TEST_PASSWORD_B",
    "MALL_TEST_ORDER_B"
)
$previousValues = @{}
foreach ($name in $temporaryNames) {
    $previousValues[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}
$resultFile = $null

try {
    $env:MALL_LIVE_DEMO_PASSWORD = $demoPassword
    $env:MALL_JAVA_BASE_URL = "http://127.0.0.1:8085"
    $resultFile = [System.IO.Path]::GetTempFileName()
    $env:MALL_LIVE_DEMO_RESULT_FILE = $resultFile
    $setupOutput = & $python (Join-Path $aiProject "scripts\bootstrap_live_demo.py")
    if ($LASTEXITCODE -ne 0) {
        throw "Disposable demo account and order setup failed."
    }
    if (-not (Test-Path -LiteralPath $resultFile)) {
        throw "Disposable demo setup did not produce its private result file."
    }
    $demoData = (Get-Content -LiteralPath $resultFile -Raw | ConvertFrom-Json)
    $env:MALL_TEST_USER_A = $demoData.account_a.username
    $env:MALL_TEST_PASSWORD_A = $demoPassword
    $env:MALL_TEST_ORDER_A = $demoData.account_a.order_sn
    $env:MALL_TEST_USER_B = $demoData.account_b.username
    $env:MALL_TEST_PASSWORD_B = $demoPassword
    $env:MALL_TEST_ORDER_B = $demoData.account_b.order_sn

    & $python (Join-Path $aiProject "scripts\verify_auth_flow.py")
    if ($LASTEXITCODE -ne 0) {
        throw "Two-account login and order-ownership verification failed."
    }

    Write-Host "Local demo data is ready:"
    Write-Host "  Account A: $($demoData.account_a.username)"
    Write-Host "  Account B: $($demoData.account_b.username)"
    Write-Host "The password was not written to a file or the console. Use it to log in through the browser."
} finally {
    if ($resultFile -and (Test-Path -LiteralPath $resultFile)) {
        Remove-Item -LiteralPath $resultFile -Force -ErrorAction SilentlyContinue
    }
    foreach ($name in $temporaryNames) {
        if ($null -eq $previousValues[$name]) {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        } else {
            [Environment]::SetEnvironmentVariable($name, $previousValues[$name], "Process")
        }
    }
}

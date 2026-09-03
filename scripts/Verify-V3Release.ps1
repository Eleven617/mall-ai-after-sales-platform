[CmdletBinding()]
param(
    [switch]$SkipJava
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$service = Join-Path $root "mall-ai-service"
$python = Join-Path $service ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "未找到 mall-ai-service/.venv。请先按 README 安装 requirements-dev.txt。"
}

Push-Location $service
try {
    & $python -m compileall -q app
    if ($LASTEXITCODE -ne 0) { throw "FastAPI compile 失败。" }
    & $python -m pytest --collect-only -q
    if ($LASTEXITCODE -ne 0) { throw "FastAPI collect 失败。" }
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "FastAPI 回归失败。" }
    & $python scripts\validate_v3_release_manifest.py --json
    if ($LASTEXITCODE -ne 0) { throw "v3 manifest 校验失败。" }
    & $python scripts\run_v3_release_preflight.py --json
    if ($LASTEXITCODE -ne 0) { throw "v3 deterministic preflight 失败。" }
} finally {
    Pop-Location
}

Push-Location (Join-Path $root "mall-ai-web")
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "Web 依赖安装失败。" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Web 构建失败。" }
} finally {
    Pop-Location
}

if (-not $SkipJava) {
    Push-Location (Join-Path $root "mall2")
    try {
        mvn -pl mall-portal -am "-DskipTests=false" "-Dsurefire.failIfNoSpecifiedTests=false" test
        if ($LASTEXITCODE -ne 0) { throw "Java portal 测试失败。" }
        mvn -pl mall-admin -am "-DskipTests=false" "-Dsurefire.failIfNoSpecifiedTests=false" test
        if ($LASTEXITCODE -ne 0) { throw "Java admin 测试失败。" }
    } finally {
        Pop-Location
    }
}

Push-Location $root
try {
    docker compose --env-file .env.example config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Compose 合同失败。" }
    Write-Host "v3 release verification completed without bypassing a gate."
} finally {
    Pop-Location
}

[CmdletBinding()]
param(
    [System.Security.SecureString]$DeepSeekApiKey,
    [switch]$SkipLiveModel,
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$aiProject = Join-Path $projectRoot "mall-ai-service"
$environmentFile = Join-Path $aiProject ".env"
$environmentTemplate = Join-Path $aiProject ".env.example"
$python = Join-Path $aiProject ".venv\Scripts\python.exe"

function ConvertTo-PlainText {
    param([Parameter(Mandatory = $true)][System.Security.SecureString]$Value)

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop CLI is unavailable. Install and start Docker Desktop first."
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.12 is required to prepare the local verification environment."
}
if (-not (Test-Path -LiteralPath $environmentTemplate)) {
    throw "mall-ai-service/.env.example is missing."
}

$plainKey = $null
try {
    if (-not (Test-Path -LiteralPath $python)) {
        Push-Location $aiProject
        try {
            & python -m venv .venv
            if ($LASTEXITCODE -ne 0) {
                throw "Python virtual environment creation failed."
            }
            & .\.venv\Scripts\python.exe -m pip install --upgrade pip
            if ($LASTEXITCODE -ne 0) {
                throw "Pip upgrade failed."
            }
            & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
            if ($LASTEXITCODE -ne 0) {
                throw "Python dependency installation failed."
            }
        } finally {
            Pop-Location
        }
    }

    # A public clone deliberately has no model weights or Chroma index. Build
    # them from committed policy Markdown before starting containers; this step
    # never reads a DeepSeek key or customer data.
    $ragBootstrap = Join-Path $aiProject "scripts\prepare_local_rag.py"
    & $python $ragBootstrap
    if ($LASTEXITCODE -ne 0) {
        throw "Local RAG bootstrap failed. Check normal network access for the first embedding-model download."
    }

    if (-not (Test-Path -LiteralPath $environmentFile)) {
        Copy-Item -LiteralPath $environmentTemplate -Destination $environmentFile
        if ($SkipLiveModel) {
            Write-Host "Created a local .env without a live-model key. Contract tests and RAG setup work; live chat will safely stop until you add your own key."
        } else {
            if ($null -eq $DeepSeekApiKey) {
                $DeepSeekApiKey = Read-Host "Enter your own DeepSeek API key for local live chat" -AsSecureString
            }
            $plainKey = ConvertTo-PlainText -Value $DeepSeekApiKey
            if ([string]::IsNullOrWhiteSpace($plainKey)) {
                throw "A DeepSeek API key is required unless -SkipLiveModel is selected."
            }
            $content = Get-Content -LiteralPath $environmentFile -Raw
            $content = $content -replace '(?m)^DEEPSEEK_API_KEY=.*$', ("DEEPSEEK_API_KEY=" + $plainKey)
            Set-Content -LiteralPath $environmentFile -Value $content -Encoding utf8NoBOM
            Write-Host "Created a local .env. The API key is ignored by Git and was not printed."
        }
    }

    $startParameters = @{}
    if ($SkipBuild) {
        $startParameters.SkipBuild = $true
    }
    $startParameters.SkipRagBootstrap = $true
    & (Join-Path $PSScriptRoot "start-demo.ps1") @startParameters
    if ($LASTEXITCODE -ne 0) {
        throw "Local public-demo preparation failed."
    }
} finally {
    $plainKey = $null
    $DeepSeekApiKey = $null
}

[CmdletBinding()]
param(
    [System.Security.SecureString]$DemoPassword,
    [switch]$PrepareCustomerFixtures,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $projectRoot "docker-compose.yml"
$aiProject = Join-Path $projectRoot "mall-ai-service"
$python = Join-Path $aiProject ".venv\Scripts\python.exe"

# These names are intentionally stable so the local demo is usable without
# recovering a password from an old test run.  Only the local Compose MySQL
# service is touched; no runtime API receives a privileged bootstrap path.
$operatorUsername = "localDemoOperations"
$qualityUsername = "aiQualityDeveloper"
$processorUsername = "afterSalesProcessor"
$customerAUsername = "localDemoCustomerA"
$customerBUsername = "localDemoCustomerB"
$temporaryEnvironmentNames = @("MALL_LOCAL_DEMO_PASSWORD", "MALL_LIVE_DEMO_PASSWORD", "MALL_JAVA_BASE_URL", "MALL_LIVE_DEMO_USER_A", "MALL_LIVE_DEMO_USER_B", "MALL_LIVE_DEMO_RESULT_FILE")
$localAiServiceBaseUrl = "http://127.0.0.1:8000"

function ConvertTo-PlainText {
    param([Parameter(Mandatory = $true)][System.Security.SecureString]$Value)

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Restore-ProcessEnvironment {
    param([Parameter(Mandatory = $true)][hashtable]$PreviousValues)

    foreach ($name in $PreviousValues.Keys) {
        if ($null -eq $PreviousValues[$name]) {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        } else {
            [Environment]::SetEnvironmentVariable($name, $PreviousValues[$name], "Process")
        }
    }
}

function Assert-LocalAiServiceReady {
    param([Parameter(Mandatory = $true)][string]$BaseUrl)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/health/ready" -TimeoutSec 10
    } catch {
        throw "The local AI service is not ready. Start the demo first with .\scripts\start-demo.ps1."
    }
    if ($response.StatusCode -ne 200) {
        throw "The local AI service is not ready. Start the demo first with .\scripts\start-demo.ps1."
    }
}

function Assert-LocalDemoLogin {
    param(
        [Parameter(Mandatory = $true)][string]$BaseUrl,
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Username,
        [Parameter(Mandatory = $true)][string]$Password,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $body = @{ username = $Username; password = $Password } | ConvertTo-Json -Compress
    try {
        $response = Invoke-RestMethod -Method Post -Uri "$BaseUrl$Path" -ContentType "application/json" -Body $body -TimeoutSec 15
    } catch {
        throw "$Label login verification failed. The account change was committed, but please restart the local demo and run this script again."
    }
    if ($null -eq $response -or [string]::IsNullOrWhiteSpace([string]$response.authorization)) {
        throw "$Label login verification returned an invalid response. Run this script again after the local demo is healthy."
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop CLI is unavailable. Start Docker Desktop first."
}
if (-not (Test-Path -LiteralPath $composeFile)) {
    throw "docker-compose.yml is missing. Run this script from the checked-out Mall project."
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python virtual environment is missing: $python"
}
Assert-LocalAiServiceReady -BaseUrl $localAiServiceBaseUrl

if ($null -eq $DemoPassword) {
    $DemoPassword = Read-Host "Set one password for local demo identities" -AsSecureString
}

$plainPassword = $null
$previousEnvironment = @{}
foreach ($name in $temporaryEnvironmentNames) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

try {
    $plainPassword = ConvertTo-PlainText -Value $DemoPassword
    if ([string]::IsNullOrWhiteSpace($plainPassword)) {
        throw "The local demo password cannot be empty."
    }
    $passwordBytes = [System.Text.Encoding]::UTF8.GetBytes($plainPassword)
    if ($passwordBytes.Length -lt 12 -or $passwordBytes.Length -gt 72) {
        throw "Use a local demo password between 12 and 72 UTF-8 bytes."
    }

    & docker compose -f $composeFile exec -T mysql sh -ec 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --protocol=TCP --host=127.0.0.1 --port=3306 --user=root --execute="SELECT 1" mall >/dev/null'
    if ($LASTEXITCODE -ne 0) {
        throw "The local MySQL container is not ready. Start the demo first with .\scripts\start-demo.ps1."
    }

    [Environment]::SetEnvironmentVariable("MALL_LOCAL_DEMO_PASSWORD", $plainPassword, "Process")
    $hashOutput = & $python -c 'import os, bcrypt; print(bcrypt.hashpw(os.environ["MALL_LOCAL_DEMO_PASSWORD"].encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii"))'
    if ($LASTEXITCODE -ne 0) {
        throw "The local BCrypt helper could not create a password hash."
    }
    $passwordHash = ($hashOutput | Select-Object -Last 1).Trim()
    if ($passwordHash -notmatch '^\$2[aby]\$12\$[./A-Za-z0-9]{53}$') {
        throw "The local BCrypt helper returned an invalid password hash."
    }

    $transactionEnd = if ($DryRun) { "ROLLBACK;" } else { "COMMIT;" }
    $bootstrapSql = @'
set -eu
MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --protocol=TCP --host=127.0.0.1 --port=3306 --user=root --default-character-set=utf8mb4 mall <<SQL
START TRANSACTION;
SET @demo_password_hash = '$MALL_LOCAL_DEMO_PASSWORD_HASH';

INSERT INTO ums_role (name, description, admin_count, create_time, status, sort)
SELECT 'AI质量开发者', '只能访问合成 AI 质量评测页面', 0, NOW(), 1, 0
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM ums_role WHERE name = 'AI质量开发者');

INSERT INTO ums_role (name, description, admin_count, create_time, status, sort)
SELECT '售后处理人员', '只能领取和处理最小化 AI 转人工案件', 0, NOW(), 1, 0
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM ums_role WHERE name = '售后处理人员');

INSERT INTO ums_admin (username, password, icon, email, nick_name, note, create_time, login_time, status)
SELECT 'localDemoOperations', @demo_password_hash, NULL, NULL, '本地演示运营人员', '本地 Compose 演示专用账号', NOW(), NULL, 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM ums_admin WHERE username = 'localDemoOperations');

INSERT INTO ums_admin (username, password, icon, email, nick_name, note, create_time, login_time, status)
SELECT 'aiQualityDeveloper', @demo_password_hash, NULL, NULL, 'AI质量开发者', '本地合成评测专用账号', NOW(), NULL, 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM ums_admin WHERE username = 'aiQualityDeveloper');

INSERT INTO ums_admin (username, password, icon, email, nick_name, note, create_time, login_time, status)
SELECT 'afterSalesProcessor', @demo_password_hash, NULL, NULL, '售后处理人员', '本地人工协同演示专用账号', NOW(), NULL, 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM ums_admin WHERE username = 'afterSalesProcessor');

UPDATE ums_admin
SET password = @demo_password_hash, status = 1, login_time = NULL
WHERE username IN ('localDemoOperations', 'aiQualityDeveloper', 'afterSalesProcessor');

INSERT INTO ums_admin_role_relation (admin_id, role_id)
SELECT admin.id, role.id
FROM ums_admin AS admin
JOIN ums_role AS role ON role.name = '订单管理员'
WHERE admin.username = 'localDemoOperations'
  AND NOT EXISTS (
      SELECT 1 FROM ums_admin_role_relation AS relation_record
      WHERE relation_record.admin_id = admin.id AND relation_record.role_id = role.id
  );

INSERT INTO ums_admin_role_relation (admin_id, role_id)
SELECT admin.id, role.id
FROM ums_admin AS admin
JOIN ums_role AS role ON role.name = 'AI质量开发者'
WHERE admin.username = 'aiQualityDeveloper'
  AND NOT EXISTS (
      SELECT 1 FROM ums_admin_role_relation AS relation_record
      WHERE relation_record.admin_id = admin.id AND relation_record.role_id = role.id
  );

INSERT INTO ums_admin_role_relation (admin_id, role_id)
SELECT admin.id, role.id
FROM ums_admin AS admin
JOIN ums_role AS role ON role.name = '售后处理人员'
WHERE admin.username = 'afterSalesProcessor'
  AND NOT EXISTS (
      SELECT 1 FROM ums_admin_role_relation AS relation_record
      WHERE relation_record.admin_id = admin.id AND relation_record.role_id = role.id
  );

UPDATE ums_member
SET password = @demo_password_hash, status = 1
WHERE username IN ('localDemoCustomerA', 'localDemoCustomerB');

__TRANSACTION_END__
SQL
'@.Replace("__TRANSACTION_END__", $transactionEnd)

    & docker compose -f $composeFile exec -T -e "MALL_LOCAL_DEMO_PASSWORD_HASH=$passwordHash" mysql sh -ec $bootstrapSql
    if ($LASTEXITCODE -ne 0) {
        throw "Local demo identity provisioning failed; no partial database transaction was committed."
    }

    if ($DryRun) {
        Write-Host "Local demo identity dry run passed. No account or password change was committed."
        return
    }

    # Password verification reads cached account snapshots in the two Java
    # services.  Delete only the known local-demo cache keys after the
    # transaction commits; do not flush Redis or touch other users.
    $cacheKeys = @(
        "mall:ums:admin:$operatorUsername",
        "mall:ums:admin:$qualityUsername",
        "mall:ums:admin:$processorUsername",
        "mall:ums:member:$customerAUsername",
        "mall:ums:member:$customerBUsername"
    )
    & docker compose -f $composeFile exec -T redis redis-cli DEL @cacheKeys *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Demo identities were committed, but the exact local auth-cache keys could not be cleared. Restart the two Java services before logging in."
    }

    if ($PrepareCustomerFixtures) {
        $customerCountOutput = & docker compose -f $composeFile exec -T mysql sh -ec 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --protocol=TCP --host=127.0.0.1 --port=3306 --user=root --skip-column-names --batch --execute="SELECT COUNT(*) FROM ums_member WHERE username IN (''localDemoCustomerA'', ''localDemoCustomerB'')" mall'
        if ($LASTEXITCODE -ne 0) {
            throw "Internal role accounts are ready, but existing local customer fixtures could not be checked."
        }
        $customerCount = 0
        $customerCountText = ($customerCountOutput | Select-Object -Last 1).Trim()
        if (-not [int]::TryParse($customerCountText, [ref]$customerCount)) {
            throw "The local customer-fixture check returned an invalid result."
        }
        if ($customerCount -lt 2) {
            [Environment]::SetEnvironmentVariable("MALL_LIVE_DEMO_PASSWORD", $plainPassword, "Process")
            [Environment]::SetEnvironmentVariable("MALL_JAVA_BASE_URL", "http://127.0.0.1:8085", "Process")
            [Environment]::SetEnvironmentVariable("MALL_LIVE_DEMO_USER_A", $customerAUsername, "Process")
            [Environment]::SetEnvironmentVariable("MALL_LIVE_DEMO_USER_B", $customerBUsername, "Process")
            $resultFile = $null
            $resultFile = [System.IO.Path]::GetTempFileName()
            try {
                [Environment]::SetEnvironmentVariable("MALL_LIVE_DEMO_RESULT_FILE", $resultFile, "Process")
                $fixtureOutput = & $python (Join-Path $aiProject "scripts\bootstrap_live_demo.py")
                if ($LASTEXITCODE -ne 0) {
                    throw "Internal role accounts are ready, but local customer fixtures could not be prepared."
                }
                if (-not (Test-Path -LiteralPath $resultFile)) {
                    throw "Local customer bootstrap did not produce its private result file."
                }
                # Parse only the short-lived private result needed by the
                # caller.  Never persist or print its synthetic identifiers.
                $null = (Get-Content -LiteralPath $resultFile -Raw | ConvertFrom-Json)
            } finally {
                if (Test-Path -LiteralPath $resultFile) {
                    Remove-Item -LiteralPath $resultFile -Force -ErrorAction SilentlyContinue
                }
            }
        } else {
            Write-Host "Existing local customer fixtures were retained; no additional synthetic order was created."
        }
    }

    # Verify through the same FastAPI boundaries that the browser uses.  The
    # returned JWTs never leave this process; this is only a post-write proof
    # that the local password reset and role assignments are usable.
    $loginChecks = @(
        [pscustomobject]@{ Path = "/operations/auth/login"; Username = $operatorUsername; Label = "Operations" },
        [pscustomobject]@{ Path = "/quality/auth/login"; Username = $qualityUsername; Label = "Quality developer" },
        [pscustomobject]@{ Path = "/service-operations/auth/login"; Username = $processorUsername; Label = "Service processor" }
    )
    if ($PrepareCustomerFixtures) {
        $loginChecks += @(
            [pscustomobject]@{ Path = "/auth/login"; Username = $customerAUsername; Label = "Customer A" },
            [pscustomobject]@{ Path = "/auth/login"; Username = $customerBUsername; Label = "Customer B" }
        )
    }
    foreach ($check in $loginChecks) {
        Assert-LocalDemoLogin -BaseUrl $localAiServiceBaseUrl -Path $check.Path -Username $check.Username -Password $plainPassword -Label $check.Label
    }

    Write-Host "Local demo identities are ready and their applicable login boundaries were verified. The password was supplied by you and was not written to a file or printed."
    Write-Host "  Customer A: $customerAUsername"
    Write-Host "  Customer B: $customerBUsername"
    Write-Host "  Operations: $operatorUsername"
    Write-Host "  Quality developer: $qualityUsername"
    Write-Host "  Service processor: $processorUsername"
    if (-not $PrepareCustomerFixtures) {
        Write-Host "Customer accounts were not created in this run. Add -PrepareCustomerFixtures to create the two local synthetic customer fixtures."
    }
} finally {
    Restore-ProcessEnvironment -PreviousValues $previousEnvironment
    $plainPassword = $null
    $DemoPassword = $null
}

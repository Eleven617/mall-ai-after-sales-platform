from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "Initialize-LocalDemoAccess.ps1"
PORTFOLIO_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "Run-V3_0_3-Portfolio-Release.ps1"


def test_local_demo_identity_script_keeps_mysql_sql_off_native_command_line() -> None:
    """Keep the Windows PowerShell 5.1 Docker argument-passing regression covered."""

    content = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "function Invoke-ComposeMysqlSql" in content
    assert "$OutputEncoding = $utf8NoBom" in content
    assert "[Console]::OutputEncoding = $utf8NoBom" in content
    assert "$Sql | & docker compose -f $composeFile exec -T mysql sh -c $mysqlCommand" in content
    assert "${IFS}" in content
    assert "$hashProgram | & $python" in content
    assert "sh -ec $bootstrapSql" not in content
    assert "--execute=\"SELECT 1\"" not in content


def test_portfolio_release_treats_the_denied_provider_guard_as_a_preflight_pass() -> None:
    """The no-network guard check must not abort before a formal batch exists."""

    content = PORTFOLIO_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "$PSNativeCommandUseErrorActionPreference = $false" in content
    assert "$guardExitCode = $LASTEXITCODE" in content
    assert "if ($guardExitCode -eq 0)" in content

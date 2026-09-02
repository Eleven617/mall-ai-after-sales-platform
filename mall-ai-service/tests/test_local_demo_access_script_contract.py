from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "Initialize-LocalDemoAccess.ps1"


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

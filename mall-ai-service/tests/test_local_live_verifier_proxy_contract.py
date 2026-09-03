"""Regression contract for local Compose verification clients.

These scripts deliberately target loopback services.  They must not inherit a
host system proxy, because that can send ``127.0.0.1`` through a corporate/VPN
proxy and report a misleading 502 while the local Docker service is healthy.
"""

from pathlib import Path


SCRIPT_NAMES = (
    "bootstrap_live_demo.py",
    "verify_auth_flow.py",
    "verify_build14_live.py",
    "verify_build21_authenticated_live.py",
    "verify_compose_stack.py",
    "verify_mcp_authenticated_live.py",
    "verify_return_status_flow.py",
    "verify_service_case_live.py",
    "verify_unified_after_sales_live.py",
)


def test_local_live_verifiers_disable_host_proxy_inheritance() -> None:
    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    for script_name in SCRIPT_NAMES:
        source = (scripts_dir / script_name).read_text(encoding="utf-8")
        assert "trust_env=False" in source, script_name

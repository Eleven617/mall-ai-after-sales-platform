"""Small dependency-light Chrome CDP helper for the field runner.

It intentionally exposes only page readiness, route/surface and safe-public
assertions. Credentials are supplied in memory and never printed or written to
the evidence JSON.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import requests
import websocket


ROOT = Path(__file__).resolve().parents[2]
BASE = os.getenv("MALL_DEMO_WEB_BASE_URL", "http://127.0.0.1:5173").rstrip("/")


class _Page:
    def __init__(self, url: str) -> None:
        self.ws = websocket.create_connection(url, timeout=30)
        self._next_id = 0

    def close(self) -> None:
        self.ws.close()

    def command(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._next_id += 1
        message_id = self._next_id
        self.ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            value = json.loads(self.ws.recv())
            if value.get("id") == message_id:
                if "error" in value:
                    raise RuntimeError(f"cdp_{method}_failed")
                return value.get("result", {})

    def evaluate(self, expression: str) -> Any:
        result = self.command(
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": True, "returnByValue": True, "userGesture": True},
        )
        if result.get("exceptionDetails"):
            raise RuntimeError("page_evaluation_failed")
        return result.get("result", {}).get("value")

    def navigate(self, url: str) -> None:
        self.command("Page.navigate", {"url": url})
        self.wait_for("document.readyState === 'complete'", timeout=30)

    def wait_for(self, expression: str, timeout: float = 30) -> Any:
        deadline = time.time() + timeout
        while time.time() < deadline:
            value = self.evaluate(expression)
            if value:
                return value
            time.sleep(0.25)
        raise TimeoutError("page_condition_timeout")

    def screenshot(self, path: Path) -> None:
        metrics = self.command("Page.getLayoutMetrics")
        size = metrics.get("contentSize", {})
        width = min(max(int(size.get("width", 1440)), 960), 2200)
        height = min(max(int(size.get("height", 1000)), 720), 1200)
        self.command("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})
        shot = self.command("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True, "fromSurface": True})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(shot["data"]))


class BrowserSession:
    def __init__(self, *, password: str, evidence_dir: Path) -> None:
        self.password = password
        self.evidence_dir = evidence_dir
        self.chrome: subprocess.Popen[str] | None = None
        self.page: _Page | None = None
        self.profile: Path | None = None
        self.port = 9300 + (os.getpid() % 500)
        self._customer_logged = False
        self._operations_logged = False
        self._service_logged = False

    def __enter__(self) -> "BrowserSession":
        chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        if not chrome.exists():
            chrome = Path(shutil.which("chrome") or shutil.which("google-chrome") or "")
        if not chrome.exists():
            raise RuntimeError("chrome_executable_unavailable")
        self.profile = Path(tempfile.mkdtemp(prefix="field-browser-", dir=str(ROOT / "tmp")))
        self.chrome = subprocess.Popen(
            [
                str(chrome),
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                f"--remote-debugging-port={self.port}",
                "--remote-allow-origins=*",
                f"--user-data-dir={self.profile}",
                "--window-size=1440,1000",
                BASE,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        deadline = time.time() + 30
        version: dict[str, Any] | None = None
        while time.time() < deadline:
            try:
                version = requests.get(f"http://127.0.0.1:{self.port}/json/version", timeout=2).json()
                if version.get("webSocketDebuggerUrl"):
                    break
            except Exception:
                time.sleep(0.25)
        if not version or not version.get("webSocketDebuggerUrl"):
            raise RuntimeError("chrome_cdp_unavailable")
        browser = _Page(version["webSocketDebuggerUrl"])
        target = browser.command("Target.createTarget", {"url": BASE})
        browser.close()
        target_id = target["targetId"]
        target_info: dict[str, Any] | None = None
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                items = requests.get(f"http://127.0.0.1:{self.port}/json/list", timeout=2).json()
                target_info = next((item for item in items if item.get("id") == target_id), None)
                if target_info and target_info.get("webSocketDebuggerUrl"):
                    break
            except Exception:
                time.sleep(0.25)
        if not target_info or not target_info.get("webSocketDebuggerUrl"):
            raise RuntimeError("chrome_target_unavailable")
        self.page = _Page(target_info["webSocketDebuggerUrl"])
        self.page.command("Page.enable")
        self.page.command("Runtime.enable")
        self.page.command("Network.enable")
        return self

    def __exit__(self, *_: Any) -> None:
        if self.page is not None:
            self.page.close()
        if self.chrome is not None:
            self.chrome.terminate()
            try:
                self.chrome.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.chrome.kill()
        if self.profile and self.profile.exists():
            shutil.rmtree(self.profile, ignore_errors=True)

    def open_route(self, kind: str) -> None:
        if self.page is None:
            raise RuntimeError("browser_page_unavailable")
        path = {"customer": "/", "operations": "/operations", "service_operations": "/service-operations"}.get(kind)
        if path is None:
            raise RuntimeError("unknown_browser_route")
        self.page.navigate(BASE + path + f"?field={uuid.uuid4().hex[:8]}")
        if kind == "customer" and not self._customer_logged:
            self._login_customer()
        elif kind == "operations" and not self._operations_logged:
            self._login_employee("localDemoOperations", "运营登录")
            self._operations_logged = True
        elif kind == "service_operations" and not self._service_logged:
            self._login_employee("afterSalesProcessor", "处理人员登录")
            self._service_logged = True

    def assert_ready(self) -> None:
        if self.page is None:
            raise RuntimeError("browser_page_unavailable")
        if self.page.evaluate("document.readyState === 'complete'") is not True:
            raise RuntimeError("document_not_ready")

    def assert_safe_public_text(self) -> None:
        if self.page is None:
            raise RuntimeError("browser_page_unavailable")
        text = str(self.page.evaluate("document.body.innerText || ''") or "").lower()
        if any(marker in text for marker in ("bearer ", "sk-", "api_key=", "traceback")):
            raise RuntimeError("unsafe_public_text")
        if re.search(r"(?<!\d)\d{10,}(?!\d)", text):
            raise RuntimeError("long_numeric_identifier_in_public_text")

    def assert_scenario_surface(self, scenario: str) -> None:
        if self.page is None:
            raise RuntimeError("browser_page_unavailable")
        if scenario in {"cross_role"}:
            self.page.wait_for("document.body.innerText.includes('售后运营工作台')")
        elif scenario in {"human_visibility"}:
            self.page.wait_for("document.body.innerText.includes('人工售后协同处理台')")
        elif scenario in {"create_task", "plan_revision", "clarification", "confirmation"}:
            self.page.wait_for("!!document.querySelector('textarea, input, button')")
            text = str(self.page.evaluate("document.body.innerText || ''") or "")
            if "Agent" not in text and "任务" not in text and "客服" not in text:
                raise RuntimeError("customer_task_surface_missing")
        elif scenario in {"sse_reconnect", "refresh_recovery"}:
            self.page.wait_for("!!document.querySelector('textarea, input, button')")

    def screenshot(self, path: Path) -> None:
        if self.page is None:
            raise RuntimeError("browser_page_unavailable")
        self.page.screenshot(path)

    def _login_customer(self) -> None:
        if self.page is None:
            raise RuntimeError("browser_page_unavailable")
        if self.page.evaluate("document.body.innerText.includes('已登录：localDemoCustomerA')"):
            self._customer_logged = True
            return
        self._click_text("登录")
        self.page.wait_for("!!document.querySelector('input[type=\\\"text\\\"], input:not([type])')")
        self._set_input("input[type='text'], input:not([type])", "localDemoCustomerA")
        self._set_input("input[type='password']", self.password)
        self._click_text("登录")
        self.page.wait_for("document.body.innerText.includes('已登录：localDemoCustomerA')", timeout=45)
        self._customer_logged = True

    def _login_employee(self, username: str, button: str) -> None:
        if self.page is None:
            raise RuntimeError("browser_page_unavailable")
        self.page.wait_for("!!document.querySelector('input[type=\\\"text\\\"], input:not([type])')")
        self._set_input("input[type='text'], input:not([type])", username)
        self._set_input("input[type='password']", self.password)
        self._click_text(button)
        self.page.wait_for("document.body.innerText.length > 80", timeout=45)

    def _click_text(self, text: str) -> None:
        if self.page is None:
            raise RuntimeError("browser_page_unavailable")
        value = self.page.evaluate(
            "(function(){const nodes=[...document.querySelectorAll('button,a')]; const el=nodes.find(x=>x.textContent?.trim()==="
            + json.dumps(text)
            + "); if(!el)return false; el.click(); return true;})()"
        )
        if value is not True:
            raise RuntimeError("button_not_found")

    def _set_input(self, selector: str, value: str) -> None:
        if self.page is None:
            raise RuntimeError("browser_page_unavailable")
        expression = (
            "(function(){const el=document.querySelector(%s); if(!el)return false; el.focus(); el.value=%s; "
            "el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); return true;})()"
            % (json.dumps(selector), json.dumps(value))
        )
        if self.page.evaluate(expression) is not True:
            raise RuntimeError("input_not_found")

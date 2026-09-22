from __future__ import annotations

import json

from scripts.field_browser_support import BrowserSession


def test_customer_conversation_binding_waits_for_login_initialization() -> None:
    calls: list[tuple[str, object]] = []

    class Page:
        def wait_for(self, expression, timeout=30):
            calls.append(("wait", expression))
            return True

        def evaluate(self, expression):
            calls.append(("evaluate", expression))
            return True

        def navigate(self, url):
            calls.append(("navigate", url))

    browser = BrowserSession.__new__(BrowserSession)
    browser.page = Page()
    browser.open_route = lambda kind: calls.append(("route", kind))

    browser.open_customer_conversation(
        "00000000-0000-0000-0000-000000000001",
        expected_markers=("申请取消退款",),
    )

    wait_expressions = [value for kind, value in calls if kind == "wait"]
    assert calls[0] == ("route", "customer")
    assert ".history-item.active" in wait_expressions[0]
    assert "active-conversation" in wait_expressions[1]
    assert ".agent-task-card" in wait_expressions[2]
    assert json.dumps("申请取消退款") in wait_expressions[3]

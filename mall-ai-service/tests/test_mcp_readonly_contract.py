import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.operations import OperatorProfile
from app.services.mall_client import MallAuthenticationError
from app.services.mcp_context_resolver import McpAccessScope, McpContextError, resolve_mcp_access_scope
from app.services.mcp_server import (
    MCP_PROTOCOL_HEADER,
    MCP_PROTOCOL_VERSION,
    MCP_SESSION_HEADER,
    McpSessionError,
    McpSessionStore,
    handle_mcp_request,
)
from app.services.mcp_tool_catalog import McpToolError, execute_mcp_tool, list_mcp_tools


MEMBER_SCOPE = McpAccessScope(
    subject_kind="member",
    subject_id=101,
    principal_fingerprint="member-synthetic-101",
    authorization="Bearer member-token",
    capabilities=(
        "get_order_summary",
        "get_logistics_status",
        "get_after_sales_status",
        "check_after_sales_readiness",
        "search_after_sales_policy",
    ),
)
OPERATOR_SCOPE = McpAccessScope(
    subject_kind="operator",
    subject_id=None,
    principal_fingerprint="operator-synthetic-a",
    authorization="Bearer operator-token",
    capabilities=("get_case_handoff_summary",),
)

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    MCP_PROTOCOL_HEADER: MCP_PROTOCOL_VERSION,
}


class McpReadonlyContractTests(unittest.TestCase):
    def test_member_tool_list_is_read_only_and_excludes_operations_handoff(self) -> None:
        names = {item["name"] for item in list_mcp_tools(MEMBER_SCOPE)}

        self.assertEqual(
            {
                "get_order_summary",
                "get_logistics_status",
                "get_after_sales_status",
                "check_after_sales_readiness",
                "search_after_sales_policy",
            },
            names,
        )
        forbidden_fragments = ("create", "cancel", "modify", "refund", "fulfillment", "sql", "shell", "file")
        self.assertFalse(any(fragment in name for name in names for fragment in forbidden_fragments))
        self.assertNotIn("get_case_handoff_summary", names)

    def test_operator_only_sees_minimal_case_handoff_tool(self) -> None:
        self.assertEqual(["get_case_handoff_summary"], [item["name"] for item in list_mcp_tools(OPERATOR_SCOPE)])
        with self.assertRaisesRegex(McpToolError, "不可调用"):
            execute_mcp_tool(
                name="get_order_summary",
                arguments={"orderRef": "202608280001"},
                scope=OPERATOR_SCOPE,
            )

    def test_distinct_server_derived_operators_cannot_reuse_one_mcp_session(self) -> None:
        first_operator = OperatorProfile(
            username="synthetic-operator-a",
            capabilities=["operations_analysis", "case_review"],
        )
        second_operator = OperatorProfile(
            username="synthetic-operator-b",
            capabilities=["operations_analysis", "case_review"],
        )
        with (
            patch(
                "app.services.mcp_context_resolver.get_current_member",
                side_effect=MallAuthenticationError("not a member token", 401),
            ),
            patch(
                "app.services.mcp_context_resolver.get_current_operator",
                side_effect=[first_operator, second_operator],
            ),
        ):
            first_scope = resolve_mcp_access_scope("Bearer first-operator-token")
            second_scope = resolve_mcp_access_scope("Bearer second-operator-token")

        self.assertEqual("operator", first_scope.subject_kind)
        self.assertIsNone(first_scope.subject_id)
        self.assertNotEqual(first_scope.principal_fingerprint, second_scope.principal_fingerprint)
        self.assertNotIn(first_operator.username, first_scope.principal_fingerprint)

        store = McpSessionStore()
        session_id = store.open(first_scope)
        with self.assertRaisesRegex(McpSessionError, "不存在或已失效"):
            store.require(session_id, second_scope)

    def test_extra_scope_field_is_rejected_before_any_java_read(self) -> None:
        with patch("app.services.mcp_tool_catalog.get_order_snapshot") as order_read:
            with self.assertRaisesRegex(McpToolError, "参数不符合"):
                execute_mcp_tool(
                    name="get_order_summary",
                    arguments={"orderRef": "202608280001", "memberId": 999},
                    scope=MEMBER_SCOPE,
                )

        order_read.assert_not_called()

    def test_order_tool_reuses_current_member_java_scope_and_returns_minimal_projection(self) -> None:
        snapshot = {
            "order_sn": "202608280001",
            "status": "已发货",
            "order_items": [
                {
                    "order_item_id": 33,
                    "product_name": "合成耳机",
                    "product_attr": "黑色",
                    "product_quantity": 1,
                }
            ],
        }
        with patch("app.services.mcp_tool_catalog.get_order_snapshot", return_value=snapshot) as order_read:
            result = execute_mcp_tool(
                name="get_order_summary",
                arguments={"orderRef": "202608280001"},
                scope=MEMBER_SCOPE,
            )

        order_read.assert_called_once_with("202608280001", MEMBER_SCOPE.authorization)
        self.assertEqual("java_order_fact", result["source"])
        self.assertEqual(33, result["order"]["items"][0]["itemRef"])
        self.assertNotIn("memberId", result)
        self.assertNotIn("authorization", result)

    def test_json_rpc_initialize_and_tools_list_use_server_derived_scope(self) -> None:
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "contract-test", "version": "1"},
            },
        }
        list_request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        with patch("app.services.mcp_server.resolve_mcp_access_scope", return_value=MEMBER_SCOPE):
            status, body = handle_mcp_request(initialize, "Bearer ignored-by-mock")
            list_status, list_body = handle_mcp_request(list_request, "Bearer ignored-by-mock")

        self.assertEqual(200, status)
        self.assertEqual(MCP_PROTOCOL_VERSION, body["result"]["protocolVersion"])
        self.assertEqual(200, list_status)
        self.assertNotIn("create_after_sales_application", str(list_body))

    def test_router_returns_401_for_unauthenticated_mcp_call(self) -> None:
        client = TestClient(app)
        payload = {"jsonrpc": "2.0", "id": "auth", "method": "tools/list", "params": {}}
        with patch(
            "app.routers.mcp.resolve_mcp_access_scope",
            side_effect=McpContextError("MCP 调用需要有效登录凭证。", status_code=401),
        ):
            response = client.post("/mcp", json=payload, headers=MCP_HEADERS)

        self.assertEqual(401, response.status_code)
        self.assertEqual(-32001, response.json()["error"]["code"])
        self.assertEqual(MCP_PROTOCOL_VERSION, response.headers["MCP-Protocol-Version"])

    def test_streamable_http_requires_accept_and_json_content_type_before_protocol_execution(self) -> None:
        client = TestClient(app)
        payload = {"jsonrpc": "2.0", "id": "headers", "method": "initialize", "params": {}}

        missing_accept = client.post("/mcp", json=payload)
        wrong_content_type = client.post(
            "/mcp",
            content="{}",
            headers={"Accept": "application/json, text/event-stream", "Content-Type": "text/plain"},
        )

        self.assertEqual(406, missing_accept.status_code)
        self.assertEqual(415, wrong_content_type.status_code)

    def test_streamable_http_initializes_session_then_requires_it_for_tools_and_notification(self) -> None:
        client = TestClient(app)
        initialize = {
            "jsonrpc": "2.0",
            "id": "init",
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "contract-test", "version": "1"},
            },
        }
        with patch("app.routers.mcp.resolve_mcp_access_scope", return_value=MEMBER_SCOPE):
            initialized = client.post("/mcp", json=initialize, headers=MCP_HEADERS)
            session_id = initialized.headers[MCP_SESSION_HEADER]
            listed = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": "list", "method": "tools/list", "params": {}},
                headers={**MCP_HEADERS, MCP_SESSION_HEADER: session_id},
            )
            notification = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                headers={**MCP_HEADERS, MCP_SESSION_HEADER: session_id},
            )

        self.assertEqual(200, initialized.status_code)
        self.assertEqual("application/json", initialized.headers["content-type"])
        self.assertTrue(session_id)
        self.assertEqual(200, listed.status_code)
        self.assertEqual(session_id, listed.headers[MCP_SESSION_HEADER])
        self.assertEqual(202, notification.status_code)
        self.assertEqual("", notification.text)

    def test_streamable_http_get_requires_the_same_owner_session_and_only_emits_sse_readiness(self) -> None:
        client = TestClient(app)
        initialize = {
            "jsonrpc": "2.0",
            "id": "init-sse",
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "contract-test", "version": "1"},
            },
        }
        with patch("app.routers.mcp.resolve_mcp_access_scope", return_value=MEMBER_SCOPE):
            initialized = client.post("/mcp", json=initialize, headers=MCP_HEADERS)
            session_id = initialized.headers[MCP_SESSION_HEADER]
            sse = client.get(
                "/mcp",
                headers={
                    "Accept": "text/event-stream",
                    MCP_PROTOCOL_HEADER: MCP_PROTOCOL_VERSION,
                    MCP_SESSION_HEADER: session_id,
                },
            )

        self.assertEqual(200, sse.status_code)
        self.assertTrue(sse.headers["content-type"].startswith("text/event-stream"))
        self.assertEqual(session_id, sse.headers[MCP_SESSION_HEADER])
        self.assertIn("stream established", sse.text)
        self.assertNotIn("order", sse.text.lower())

    def test_post_after_initialize_requires_matching_protocol_header_before_tool_execution(self) -> None:
        client = TestClient(app)
        initialize = {
            "jsonrpc": "2.0",
            "id": "init-version",
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "contract-test", "version": "1"},
            },
        }
        with patch("app.routers.mcp.resolve_mcp_access_scope", return_value=MEMBER_SCOPE):
            initialized = client.post("/mcp", json=initialize, headers=MCP_HEADERS)
            session_id = initialized.headers[MCP_SESSION_HEADER]
        with patch("app.services.mcp_server.list_mcp_tools") as list_tools:
            missing = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": "missing-version", "method": "tools/list", "params": {}},
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                    MCP_SESSION_HEADER: session_id,
                },
            )
            incompatible = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": "bad-version", "method": "tools/list", "params": {}},
                headers={
                    **MCP_HEADERS,
                    MCP_PROTOCOL_HEADER: "2024-11-05",
                    MCP_SESSION_HEADER: session_id,
                },
            )

        self.assertEqual(400, missing.status_code)
        self.assertEqual(-32602, missing.json()["error"]["code"])
        self.assertEqual(400, incompatible.status_code)
        self.assertEqual(-32602, incompatible.json()["error"]["code"])
        list_tools.assert_not_called()

    def test_initialize_rejects_a_conflicting_protocol_header_without_opening_session(self) -> None:
        client = TestClient(app)
        payload = {
            "jsonrpc": "2.0",
            "id": "init-bad-header",
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "contract-test", "version": "1"},
            },
        }
        with patch("app.routers.mcp.resolve_mcp_access_scope", return_value=MEMBER_SCOPE):
            response = client.post(
                "/mcp",
                json=payload,
                headers={**MCP_HEADERS, MCP_PROTOCOL_HEADER: "2024-11-05"},
            )

        self.assertEqual(400, response.status_code)
        self.assertEqual(-32602, response.json()["error"]["code"])
        self.assertNotIn(MCP_SESSION_HEADER, response.headers)

    def test_initialize_rejects_nested_scope_or_write_parameters_before_opening_session(self) -> None:
        client = TestClient(app)
        payload = {
            "jsonrpc": "2.0",
            "id": "init-forbidden-params",
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"experimental": {"memberId": 999, "write": True}},
                "clientInfo": {"name": "contract-test", "version": "1"},
            },
        }
        with (
            patch("app.routers.mcp.resolve_mcp_access_scope", return_value=MEMBER_SCOPE),
            patch("app.routers.mcp.mcp_session_store.open") as open_session,
        ):
            response = client.post("/mcp", json=payload, headers=MCP_HEADERS)

        self.assertEqual(400, response.status_code)
        self.assertEqual(-32600, response.json()["error"]["code"])
        self.assertNotIn(MCP_SESSION_HEADER, response.headers)
        open_session.assert_not_called()

    def test_initialize_rejects_excessively_nested_metadata_before_opening_session(self) -> None:
        client = TestClient(app)
        nested_capability: dict[str, object] = {}
        cursor = nested_capability
        for index in range(10):
            child: dict[str, object] = {}
            cursor[f"layer{index}"] = child
            cursor = child
        payload = {
            "jsonrpc": "2.0",
            "id": "init-deep-params",
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": nested_capability,
                "clientInfo": {"name": "contract-test", "version": "1"},
            },
        }
        with (
            patch("app.routers.mcp.resolve_mcp_access_scope", return_value=MEMBER_SCOPE),
            patch("app.routers.mcp.mcp_session_store.open") as open_session,
        ):
            response = client.post("/mcp", json=payload, headers=MCP_HEADERS)

        self.assertEqual(400, response.status_code)
        self.assertEqual(-32600, response.json()["error"]["code"])
        self.assertNotIn(MCP_SESSION_HEADER, response.headers)
        open_session.assert_not_called()

    def test_streamable_http_rejects_missing_or_cross_subject_sessions_without_reading_tools(self) -> None:
        client = TestClient(app)
        initialize = {
            "jsonrpc": "2.0",
            "id": "init-cross",
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "contract-test", "version": "1"},
            },
        }
        with patch("app.routers.mcp.resolve_mcp_access_scope", return_value=MEMBER_SCOPE):
            initialized = client.post("/mcp", json=initialize, headers=MCP_HEADERS)
            session_id = initialized.headers[MCP_SESSION_HEADER]
            missing = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": "missing", "method": "tools/list", "params": {}},
                headers=MCP_HEADERS,
            )
        foreign_scope = McpAccessScope(
            subject_kind="member",
            subject_id=202,
            principal_fingerprint="member-synthetic-202",
            authorization="Bearer another-member-token",
            capabilities=MEMBER_SCOPE.capabilities,
        )
        with (
            patch("app.routers.mcp.resolve_mcp_access_scope", return_value=foreign_scope),
            patch("app.services.mcp_server.list_mcp_tools") as list_tools,
        ):
            cross_subject = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": "cross", "method": "tools/list", "params": {}},
                headers={**MCP_HEADERS, MCP_SESSION_HEADER: session_id},
            )

        self.assertEqual(400, missing.status_code)
        self.assertEqual(404, cross_subject.status_code)
        list_tools.assert_not_called()

    def test_streamable_http_rejects_invalid_notification_id_and_allows_explicit_session_close(self) -> None:
        client = TestClient(app)
        initialize = {
            "jsonrpc": "2.0",
            "id": "init-close",
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "contract-test", "version": "1"},
            },
        }
        with patch("app.routers.mcp.resolve_mcp_access_scope", return_value=MEMBER_SCOPE):
            initialized = client.post("/mcp", json=initialize, headers=MCP_HEADERS)
            session_id = initialized.headers[MCP_SESSION_HEADER]
            invalid_notification = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": "unexpected", "method": "notifications/initialized", "params": {}},
                headers={**MCP_HEADERS, MCP_SESSION_HEADER: session_id},
            )
            closed = client.delete(
                "/mcp",
                headers={
                    "Authorization": MEMBER_SCOPE.authorization,
                    MCP_PROTOCOL_HEADER: MCP_PROTOCOL_VERSION,
                    MCP_SESSION_HEADER: session_id,
                },
            )
            after_close = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": "after-close", "method": "tools/list", "params": {}},
                headers={**MCP_HEADERS, MCP_SESSION_HEADER: session_id},
            )

        self.assertEqual(400, invalid_notification.status_code)
        self.assertEqual(-32600, invalid_notification.json()["error"]["code"])
        self.assertEqual(204, closed.status_code)
        self.assertEqual(404, after_close.status_code)


if __name__ == "__main__":
    unittest.main()

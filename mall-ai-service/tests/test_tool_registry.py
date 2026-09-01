import unittest

from app.schemas.tool import ToolCall
from app.services.tool_context import ToolExecutionContext
from app.services.tool_registry import (
    ToolInputError,
    call_tool,
    get_missing_required_field,
)


class ToolRegistryTests(unittest.TestCase):
    def test_required_schema_field_is_enforced_by_server(self) -> None:
        with self.assertRaises(ToolInputError):
            call_tool(
                ToolCall(name="logistics_service", arguments={}),
                ToolExecutionContext(),
            )

    def test_missing_field_helper_uses_the_same_execution_contract(self) -> None:
        self.assertEqual(
            "order_sn",
            get_missing_required_field(
                ToolCall(name="logistics_service", arguments={})
            ),
        )
        self.assertIsNone(
            get_missing_required_field(
                ToolCall(
                    name="logistics_service",
                    arguments={"order_sn": "202607240001"},
                )
            )
        )


if __name__ == "__main__":
    unittest.main()

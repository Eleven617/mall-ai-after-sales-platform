from dataclasses import dataclass
from pathlib import Path
import sys


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.intent_service import detect_intent


@dataclass(frozen=True)
class IntentTestCase:
    message: str
    expected_intent: str
    expected_route: str
    expected_tool_name: str | None = None
    expected_argument_key: str | None = None
    expected_argument_value: str | None = None


TEST_CASES = [
    IntentTestCase(
        message="Redis 是什么？",
        expected_intent="general_chat",
        expected_route="chat",
    ),
    IntentTestCase(
        message="我的订单为什么还没发货？",
        expected_intent="query_order_status",
        expected_route="ask_missing_info",
        expected_tool_name="order_service",
    ),
    IntentTestCase(
        message="帮我查订单 20240617001 的物流",
        expected_intent="query_logistics",
        expected_route="tool_calling",
        expected_tool_name="logistics_service",
        expected_argument_key="order_sn",
        expected_argument_value="20240617001",
    ),
    IntentTestCase(
        message="帮我查一下 SKU10001 还有多少库存",
        expected_intent="query_inventory",
        expected_route="tool_calling",
        expected_tool_name="inventory_service",
        expected_argument_key="sku_id",
        expected_argument_value="SKU10001",
    ),
    IntentTestCase(
        message="退货运费谁承担？",
        expected_intent="after_sales_policy",
        expected_route="rag",
    ),
    IntentTestCase(
        message="最近 7 天销量为什么下降？",
        expected_intent="business_analysis",
        expected_route="agent",
        expected_tool_name="analysis_agent",
    ),
]


def main() -> None:
    passed = 0

    for index, case in enumerate(TEST_CASES, start=1):
        intent = detect_intent(case.message)
        errors = _validate(case, intent)

        status = "PASS" if not errors else "FAIL"
        print(f"\n[{index}] {status} {case.message}")
        print(intent.model_dump_json(indent=2))

        if errors:
            for error in errors:
                print(f"  - {error}")
            print(f"  建议：{_suggest_fix(errors)}")
        else:
            passed += 1

    print(f"\nResult: {passed}/{len(TEST_CASES)} passed")


def _validate(case: IntentTestCase, intent) -> list[str]:
    errors: list[str] = []

    if intent.intent != case.expected_intent:
        errors.append(f"intent expected {case.expected_intent}, got {intent.intent}")

    if intent.route != case.expected_route:
        errors.append(f"route expected {case.expected_route}, got {intent.route}")

    actual_tool_name = intent.tool_call.name if intent.tool_call else None
    if actual_tool_name != case.expected_tool_name:
        errors.append(
            f"tool name expected {case.expected_tool_name}, got {actual_tool_name}"
        )

    if case.expected_argument_key:
        actual_value = None
        if intent.tool_call:
            actual_value = intent.tool_call.arguments.get(case.expected_argument_key)

        if actual_value != case.expected_argument_value:
            errors.append(
                f"argument {case.expected_argument_key} expected "
                f"{case.expected_argument_value}, got {actual_value}"
            )

    return errors


def _suggest_fix(errors: list[str]) -> str:
    joined = " ".join(errors)
    if "intent expected" in joined or "route expected" in joined:
        return "优先调整 intent_service.py 里的 INTENT_SYSTEM_PROMPT，让模型更清楚分类规则。"
    if "tool name expected" in joined:
        return "优先检查 Prompt 里的工具名规则，以及 tool_registry.py 是否注册了该工具。"
    if "argument" in joined:
        return "优先调整 Prompt 的参数提取规则，例如 order_sn、sku_id 应该放进 tool_call.arguments。"

    return "先查看模型实际输出，再判断是 Prompt、Schema 还是工具注册问题。"


if __name__ == "__main__":
    main()

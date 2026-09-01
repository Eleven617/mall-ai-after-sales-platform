import unittest

from app.services.fact_presentation_service import (
    build_verified_facts,
    render_verified_facts_summary,
)


class FactPresentationServiceTests(unittest.TestCase):
    def test_exposes_only_allow_listed_order_fields(self) -> None:
        facts = build_verified_facts(
            [
                (
                    "order_service",
                    {
                        "order_sn": "202607240001",
                        "status": "已发货",
                        "product_names": ["无线耳机", "手机壳"],
                        "delivery_company": "测试物流",
                        "tracking_no": "TEST-001",
                        "order_items": [{"order_item_id": 501}],
                    },
                )
            ]
        )

        rendered = render_verified_facts_summary(facts)
        dumped = facts[0].model_dump_json()

        self.assertIn("已发货", rendered)
        self.assertIn("无线耳机、手机壳", rendered)
        self.assertNotIn("order_item_id", dumped)
        self.assertNotIn("501", dumped)

    def test_marks_inventory_as_demo_until_java_integration_exists(self) -> None:
        facts = build_verified_facts(
            [
                (
                    "inventory_service",
                    {
                        "sku_id": "SKU10001",
                        "available_stock": 86,
                        "reserved_stock": 14,
                        "warehouse": "华东仓",
                        "status": "in_stock",
                    },
                )
            ]
        )

        self.assertEqual("库存信息（当前演示数据）", facts[0].title)


if __name__ == "__main__":
    unittest.main()

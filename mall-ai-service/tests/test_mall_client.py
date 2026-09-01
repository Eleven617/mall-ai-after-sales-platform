import unittest
from unittest.mock import Mock, patch

from app.services.mall_client import (
    MallApiClientError,
    MallOrderNotAccessibleError,
    create_after_sales_application,
    get_order_snapshot,
)


class MallApiClientTests(unittest.TestCase):
    @patch("app.services.mall_client.httpx.get")
    def test_returns_only_the_ai_order_snapshot(self, http_get: Mock) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {
            "code": 200,
            "message": "操作成功",
            "data": {
                "orderSn": "202607240001",
                "status": 2,
                "statusText": "已发货",
                "deliveryCompany": "顺丰速运",
                "deliverySn": "SF1234567890",
                "productNames": ["无线耳机"],
                "orderItems": [
                    {
                        "orderItemId": 501,
                        "productName": "无线耳机",
                        "productAttr": "颜色：黑色",
                        "productQuantity": 2,
                        "productPrice": "199.00",
                    }
                ],
                "receiverPhone": "13800000000",
            },
        }
        http_get.return_value = response

        snapshot = get_order_snapshot(
            "202607240001",
            "Bearer user-token",
        )

        self.assertEqual("202607240001", snapshot["order_sn"])
        self.assertEqual("已发货", snapshot["status"])
        self.assertEqual(["无线耳机"], snapshot["product_names"])
        self.assertEqual(
            [{
                "order_item_id": 501,
                "product_name": "无线耳机",
                "product_attr": "颜色：黑色",
                "product_quantity": 2,
            }],
            snapshot["order_items"],
        )
        self.assertNotIn("productPrice", snapshot["order_items"][0])
        self.assertNotIn("receiverPhone", snapshot)
        http_get.assert_called_once()
        self.assertEqual(
            "Bearer user-token",
            http_get.call_args.kwargs["headers"]["Authorization"],
        )
        self.assertIn(
            "/order/ai/detail/by-sn/202607240001",
            http_get.call_args.args[0],
        )

    @patch("app.services.mall_client.httpx.get")
    def test_rejects_missing_bearer_token(self, http_get: Mock) -> None:
        with self.assertRaisesRegex(MallApiClientError, "请先登录"):
            get_order_snapshot("202607240001", None)
        http_get.assert_not_called()

    @patch("app.services.mall_client.httpx.get")
    def test_converts_unauthorized_response_to_safe_message(
        self,
        http_get: Mock,
    ) -> None:
        http_get.return_value = Mock(status_code=401)

        with self.assertRaisesRegex(MallApiClientError, "登录状态已失效"):
            get_order_snapshot("202607240001", "Bearer expired-token")

    @patch("app.services.mall_client.httpx.get")
    def test_marks_other_member_or_missing_order_as_non_enumerating_input_error(
        self,
        http_get: Mock,
    ) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {
            "code": 500,
            "message": "订单不存在或无权访问！",
        }
        http_get.return_value = response

        with self.assertRaisesRegex(MallOrderNotAccessibleError, "当前账号可查询"):
            get_order_snapshot("202607240001", "Bearer user-token")

    @patch("app.services.mall_client.httpx.post")
    def test_generic_after_sales_write_carries_internal_capability(
        self,
        http_post: Mock,
    ) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {
            "code": 200,
            "data": {
                "applicationId": 801,
                "orderSn": "202607240001",
                "applicationType": "exchange",
                "applicationTypeLabel": "换货",
                "productName": "无线耳机",
                "productAttr": "颜色：黑色",
                "reason": "质量问题",
                "description": "无法充电",
                "status": "pending_review",
                "statusLabel": "待审核",
                "createdAt": 1720000000000,
                "updatedAt": 1720000000000,
                "handlingNote": None,
                "canCancel": True,
                "canModify": True,
            },
        }
        http_post.return_value = response

        created = create_after_sales_application(
            order_sn="202607240001",
            application_type="exchange",
            order_item_id=501,
            reason="质量问题",
            description="无法充电",
            idempotency_key="a" * 32,
            authorization="Bearer user-token",
        )

        self.assertEqual(801, created.application_id)
        headers = http_post.call_args.kwargs["headers"]
        self.assertEqual("Bearer user-token", headers["Authorization"])
        self.assertEqual(
            "local-build21-after-sales-key",
            headers["X-AI-After-Sales-Key"],
        )


if __name__ == "__main__":
    unittest.main()

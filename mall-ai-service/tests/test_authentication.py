import unittest
from unittest.mock import Mock, patch

from app.schemas.authentication import CustomerLoginResponse, MemberProfile
from app.services.mall_client import (
    MallAuthenticationError,
    get_current_member,
    login_member,
)


class AuthenticationClientTests(unittest.TestCase):
    @patch("app.services.mall_client.httpx.get")
    @patch("app.services.mall_client.httpx.post")
    def test_login_delegates_to_java_and_returns_safe_profile(
        self,
        http_post: Mock,
        http_get: Mock,
    ) -> None:
        login_response = Mock(status_code=200)
        login_response.json.return_value = {
            "code": 200,
            "data": {"token": "java-token", "tokenHead": "Bearer "},
        }
        info_response = Mock(status_code=200)
        info_response.json.return_value = {
            "code": 200,
            "data": {
                "id": 1,
                "username": "test",
                "password": "must-not-leave-java",
                "phone": "13800000000",
            },
        }
        http_post.return_value = login_response
        http_get.return_value = info_response

        result = login_member(" test ", "123456")

        self.assertIsInstance(result, CustomerLoginResponse)
        self.assertEqual("Bearer java-token", result.authorization)
        self.assertEqual(MemberProfile(member_id=1, username="test"), result.member)
        http_post.assert_called_once()
        self.assertEqual(
            {"username": " test ", "password": "123456"},
            http_post.call_args.kwargs["data"],
        )
        self.assertEqual(
            "Bearer java-token",
            http_get.call_args.kwargs["headers"]["Authorization"],
        )

    @patch("app.services.mall_client.httpx.post")
    def test_invalid_java_credentials_are_not_returned_as_a_token(
        self,
        http_post: Mock,
    ) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {
            "code": 404,
            "message": "用户名或密码错误",
            "data": None,
        }
        http_post.return_value = response

        with self.assertRaisesRegex(MallAuthenticationError, "用户名或密码错误"):
            login_member("test", "wrong")

    @patch("app.services.mall_client.httpx.get")
    def test_current_member_rejects_invalid_token(self, http_get: Mock) -> None:
        response = Mock(status_code=401)
        response.json.return_value = {"code": 401, "message": "未登录"}
        http_get.return_value = response

        with self.assertRaisesRegex(MallAuthenticationError, "登录状态已失效"):
            get_current_member("Bearer expired")

    @patch("app.services.mall_client.httpx.get")
    def test_current_member_maps_malformed_java_profile_to_safe_error(
        self,
        http_get: Mock,
    ) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {
            "code": 200,
            "data": {"id": 0, "username": "test"},
        }
        http_get.return_value = response

        with self.assertRaisesRegex(MallAuthenticationError, "登录服务返回的数据不完整") as caught:
            get_current_member("Bearer valid-but-upstream-malformed")

        self.assertEqual(502, caught.exception.status_code)


if __name__ == "__main__":
    unittest.main()

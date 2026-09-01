import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.authentication import CustomerLoginResponse, MemberProfile
from app.services.mall_client import MallAuthenticationError


class AuthenticationRouterTests(unittest.TestCase):
    @patch("app.routers.authentication.login_member")
    def test_login_returns_java_issued_authorization_and_safe_profile(
        self,
        login_member,
    ) -> None:
        login_member.return_value = CustomerLoginResponse(
            authorization="Bearer java-token",
            member=MemberProfile(member_id=1, username="test"),
        )

        response = TestClient(app).post(
            "/auth/login",
            json={"username": "test", "password": "123456"},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "authorization": "Bearer java-token",
                "member": {"member_id": 1, "username": "test"},
            },
            response.json(),
        )
        login_member.assert_called_once_with("test", "123456")

    @patch("app.routers.authentication.get_current_member")
    def test_me_requires_and_validates_bearer_token(self, get_current_member) -> None:
        get_current_member.return_value = MemberProfile(member_id=3, username="windy")

        response = TestClient(app).get(
            "/auth/me",
            headers={"Authorization": "Bearer user-token"},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual({"member_id": 3, "username": "windy"}, response.json())
        get_current_member.assert_called_once_with("Bearer user-token")

    @patch("app.routers.authentication.get_current_member")
    def test_me_maps_invalid_java_token_to_401(self, get_current_member) -> None:
        get_current_member.side_effect = MallAuthenticationError(
            "登录状态已失效，请重新登录后再试。",
            401,
        )

        response = TestClient(app).get(
            "/auth/me",
            headers={"Authorization": "Bearer expired"},
        )

        self.assertEqual(401, response.status_code)
        self.assertIn("登录状态已失效", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()

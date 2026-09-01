import unittest

import httpx

from scripts.verify_compose_stack import _is_fastapi_ready, _is_java_ready, _is_web_page


class ComposeStackVerificationTests(unittest.TestCase):
    def test_accepts_the_expected_vue_document_response(self) -> None:
        response = httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"})

        self.assertTrue(_is_web_page(response))

    def test_requires_fastapi_ready_status(self) -> None:
        self.assertTrue(_is_fastapi_ready(httpx.Response(200, json={"status": "ok"})))
        self.assertFalse(_is_fastapi_ready(httpx.Response(503, json={"status": "unavailable"})))

    def test_requires_java_actuator_up_status(self) -> None:
        self.assertTrue(_is_java_ready(httpx.Response(200, json={"status": "UP"})))
        self.assertFalse(_is_java_ready(httpx.Response(200, json={"status": "DOWN"})))


if __name__ == "__main__":
    unittest.main()

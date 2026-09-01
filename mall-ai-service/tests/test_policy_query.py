import unittest

from app.services.policy_query import MAX_POLICY_QUERY_CHARS, project_policy_query


class PolicyQueryTests(unittest.TestCase):
    def test_removes_identifier_like_values_but_keeps_policy_terms(self) -> None:
        query = (
            "订单 202608210001 手机 13800138000 邮箱 a@example.com "
            "Bearer aaaabbbb.ccccdddd.eeeeffff 七天无理由退货可以吗？"
        )

        projected = project_policy_query(query)

        self.assertNotIn("202608210001", projected)
        self.assertNotIn("13800138000", projected)
        self.assertNotIn("a@example.com", projected)
        self.assertNotIn("aaaabbbb", projected)
        self.assertIn("七天无理由退货", projected)

    def test_normalizes_and_bounds_input_without_semantic_rewrite(self) -> None:
        projected = project_policy_query("  \u9000\u6b3e\n\t\u591a\u4e45\u5230\u8d26\uff1f  " + "x" * 1000)

        self.assertTrue(projected.startswith("\u9000\u6b3e \u591a\u4e45\u5230\u8d26?"))
        self.assertEqual(MAX_POLICY_QUERY_CHARS, len(projected))


if __name__ == "__main__":
    unittest.main()

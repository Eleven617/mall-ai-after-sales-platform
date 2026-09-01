import unittest
from pathlib import Path

from app.services.chunking_service import (
    CHUNK_OVERLAP_CHARS,
    MAX_CHUNK_CHARS,
    chunk_markdown_file,
    chunk_markdown_text,
)


class ChunkingServiceTests(unittest.TestCase):
    def test_keeps_document_and_section_metadata(self) -> None:
        knowledge_file = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "knowledge"
            / "after_sales_policy.md"
        )

        chunks = chunk_markdown_file(knowledge_file)
        return_shipping = next(chunk for chunk in chunks if chunk.title == "退货运费")

        self.assertTrue(return_shipping.chunk_id)
        self.assertEqual("after_sales_policy.md", return_shipping.source)
        self.assertEqual("售后政策知识库", return_shipping.document_title)
        self.assertEqual("售后政策知识库 > 退货运费", return_shipping.section_path)
        self.assertIn("退货运费", return_shipping.text)

    def test_contract_keeps_nested_conditions_exceptions_and_table_in_one_rule_chunk(self) -> None:
        chunks = chunk_markdown_text(
            """# 演示售后政策

> 业务规则 V2.0，更新于 2026-08-20。

类别：electronics
文档类型：policy

## 退货规则

质量问题经核验后可申请退货退款。

### 条件

- 需提交订单和商品问题凭证。

### 例外

- 已明显使用且影响二次销售时，不直接承诺退款。

### 处理表

| 商品状态 | 可申请方式 |
| --- | --- |
| 未发货 | 取消退款 |
| 已发货 | 退货退款 |
""",
            source="electronics_returns_v2.md",
        )

        self.assertEqual(1, len(chunks))
        chunk = chunks[0]
        self.assertEqual("electronics_returns_v2", chunk.document_id)
        self.assertEqual(("退货规则",), chunk.heading_path)
        self.assertEqual(1, chunk.source_order)
        self.assertEqual("V2.0", chunk.policy_version)
        self.assertEqual("2026-08-20", chunk.effective_from)
        self.assertEqual("electronics", chunk.category)
        self.assertEqual("zh-CN", chunk.language)
        self.assertEqual("policy", chunk.document_type)
        self.assertEqual(64, len(chunk.content_hash))
        for required_text in ("条件", "例外", "不直接承诺退款", "商品状态", "退货退款"):
            self.assertIn(required_text, chunk.text)

    def test_long_rule_splits_only_at_natural_boundaries_with_small_overlap(self) -> None:
        sentence_one = "条件甲" + "甲" * 620 + "。"
        sentence_two = "条件乙" + "乙" * 620 + "。"
        chunks = chunk_markdown_text(
            f"""# 长规则

> 业务规则 V3.0，更新于 2026-08-21。

## 售后规则

{sentence_one}

{sentence_two}
""",
            source="long_rule.md",
        )

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.text.endswith("。") for chunk in chunks))
        self.assertTrue(all(chunk.source_order == index for index, chunk in enumerate(chunks, 1)))
        self.assertTrue(any("条件乙" in chunk.text for chunk in chunks))
        # The policy prefix is outside the packed body; the split is allowed
        # to carry at most a small tail overlap instead of cutting a sentence.
        self.assertGreater(CHUNK_OVERLAP_CHARS, 0)
        self.assertGreater(MAX_CHUNK_CHARS, 1000)


if __name__ == "__main__":
    unittest.main()

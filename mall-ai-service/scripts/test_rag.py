"""向量 RAG 语义检索测试"""
import httpx


def test_case(name: str, message: str, session_id: str):
    print(f"【{name}】{message}")
    r = httpx.post(
        "http://127.0.0.1:8000/customer-service",
        json={"message": message, "session_id": session_id},
        timeout=120,
    )
    d = r.json()
    route = d["intent"]["route"]
    answer = d["answer"][:200]
    print(f"  Route: {route}")
    print(f"  Answer: {answer}")

    # 显示检索到的上下文
    for i, ctx in enumerate(d.get("rag_context", []) or []):
        print(f"  chunk{i+1}: {ctx[:100]}...")
    print()


def main():
    print("=== 向量 RAG 测试 ===\n")

    # 测试1：精确关键词
    test_case("测试1 精确匹配", "退货的运费谁出", "rag-1")

    # 测试2：语义相似但无关键词（旧方案做不到的）
    print("  ↓ 旧方案无法匹配 —— 不喜欢、退掉 不在关键词列表里")
    test_case("测试2 语义检索", "买回来不喜欢想退掉", "rag-2")

    # 测试3：口语化表达
    test_case("测试3 口语化", "到手发现东西有问题能换个新的不", "rag-3")

    # 测试4：带上下文展示
    test_case("测试4 超时售后", "超过7天了还能退吗", "rag-4")

    print("=== 测试完成 ===")


if __name__ == "__main__":
    main()

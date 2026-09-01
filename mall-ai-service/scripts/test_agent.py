"""Agent 功能测试 — 原生 Function Calling"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import httpx

def test(name, msg, sid="test"):
    print(f"\n=== {name} ===")
    print(f"用户：{msg}")
    r = httpx.post("http://127.0.0.1:8002/customer-service",
                    json={"message": msg, "session_id": sid}, timeout=180)
    d = r.json()
    print(f"Route: {d['intent']['route']}")
    print(f"Answer: {d['answer'][:300]}")

# 测试 1：需要查订单（会触发工具调用）
test("Agent 查订单", "我的订单123456发货了吗")

# 测试 2：需要查售后政策（触发 rag_search）
test("Agent 查政策", "退货的运费谁来承担")

# 测试 3：综合分析（会触发分析意图 → Agent 路由）
test("Agent 综合分析", "帮我查下订单123456的物流，再告诉我没发货怎么处理")

print("\n=== 完成 ===")

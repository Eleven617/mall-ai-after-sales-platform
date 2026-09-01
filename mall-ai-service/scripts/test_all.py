"""全接口测试脚本"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import httpx

BASE = "http://127.0.0.1:8002"


def show(d, desc):
    print(f"\n=== {desc} ===")
    # intent 可能是 dict 也可能是 str
    intent = d.get("intent", {})
    if isinstance(intent, dict):
        print(f"Intent: {intent.get('intent','?')} | Route: {intent.get('route','?')}")
    elif isinstance(intent, str):
        print(f"Intent: {intent} | Route: {d.get('route','?')}")
    for key in ["answer", "reply"]:
        if d.get(key):
            print(f"{key}: {d[key][:200]}")
    if d.get("rag_context"):
        for i, ctx in enumerate(d["rag_context"]):
            print(f"  chunk{i+1}: {ctx[:100]}...")


# 1. 聊天
r = httpx.post(f"{BASE}/chat", json={"message": "你好"}, timeout=60)
show(r.json(), "聊天")

# 2. 意图识别
r = httpx.post(f"{BASE}/intent", json={"message": "我的订单123456发货了吗"}, timeout=60)
show(r.json(), "意图识别 - 订单查询")

# 3. 意图识别 - 售后政策
r = httpx.post(f"{BASE}/intent", json={"message": "退货的运费谁出"}, timeout=60)
show(r.json(), "意图识别 - 售后政策")

# 4. 客服 - 工具调用
r = httpx.post(
    f"{BASE}/customer-service",
    json={"message": "我的订单123456发货了吗", "session_id": "t1"},
    timeout=120,
)
show(r.json(), "客服 - 工具调用")

# 5. 客服 - RAG 语义检索
r = httpx.post(
    f"{BASE}/customer-service",
    json={"message": "买回来不喜欢想退掉", "session_id": "t2"},
    timeout=120,
)
show(r.json(), "客服 - RAG语义检索")

print("\n=== 全部测试完成 ===")

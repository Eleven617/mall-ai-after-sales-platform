"""Agent 多工具串联测试 — 测试 run_agent() 直接调用"""
import sys, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.services.agent_service import run_agent

print("=== Agent 多工具串联测试 ===\n")

# 场景：需要查订单 + 查库存 + 查政策，Agent 要连续调多个工具
question = "我的订单123456一直没发货，帮我看看SKU10001还有没有库存，然后告诉我现在该怎么办"

print(f"用户：{question}")
print()
print("--- Agent 执行过程（看服务端日志的 [Agent Step X]）---")

answer = run_agent(question)

print()
print(f"--- 最终回答 ---")
print(answer)
print()
print("=== 完成 ===")

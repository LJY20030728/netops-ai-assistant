# -*- coding: utf-8 -*-
"""Agent 分步诊断（临时）：LLM 决策 + 工具执行。"""
import asyncio
import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(line_buffering=True)

from app.agent import agent
from app.agent.tools import execute_tool
from app.llm.zhipu_client import complete_json


async def main():
    print("[1] 测试 complete_json 决策调用 ...", flush=True)
    msgs = agent._decision_messages([], "从 core-sw-1 检查到 10.0.1.2 的连通性，并排查 OSPF 邻居为什么 DOWN", [])
    text = await complete_json(msgs)
    print("[1] 原始返回:", text[:400], flush=True)
    parsed = agent._parse_react(text)
    print("[1] 解析结果:", type(parsed).__name__, getattr(parsed, "name", ""), getattr(parsed, "arguments", ""), flush=True)
    if isinstance(parsed, agent._ToolCall):
        print("[2] 执行工具 ...", flush=True)
        result = await execute_tool(parsed.name, parsed.arguments)
        print("[2] 工具结果:", result[:300], flush=True)


asyncio.run(main())
print("DONE", flush=True)

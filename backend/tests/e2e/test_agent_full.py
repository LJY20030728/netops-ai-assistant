# -*- coding: utf-8 -*-
"""run_agent 完整循环诊断（临时）：直接消费生成器事件。"""
import asyncio
import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(line_buffering=True)

from app.agent.agent import run_agent


async def main():
    q = "从 core-sw-1 检查到 10.0.1.2 的连通性，并排查 OSPF 邻居为什么 DOWN，给出处置建议"
    print("Q:", q, flush=True)
    answer = ""
    step = 0
    async for ev in run_agent(q, []):
        t = ev.get("type")
        if t == "tool":
            step += 1
            print(f"[tool#{step}] {ev.get('tool')} ok={ev.get('ok')}", flush=True)
            print("   args:", ev.get("args"), flush=True)
            print("   result:", (ev.get("result") or "").replace("\n", " ")[:200], flush=True)
        elif t == "delta":
            answer += ev.get("content", "")
        elif t == "error":
            print("ERROR:", ev.get("message"), flush=True)
        elif t == "done":
            print("== done ==", flush=True)
    print(f"== answer len {len(answer)} ==", flush=True)
    print(answer, flush=True)


asyncio.run(main())
print("ALL DONE", flush=True)

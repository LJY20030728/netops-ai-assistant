# -*- coding: utf-8 -*-
"""场景库 × Agent 取证端到端：切换场景后跑对应排障问题，断言工具被调用且答案命中场景特征。"""
import asyncio
import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(line_buffering=True)

from app.agent.agent import run_agent
from app.agent.devices import set_current_scenario

PASS = 0
FAIL = 0

CASES = [
    # (场景, 示例问题, 答案特征关键词列表)
    ("flapping", "从 core-sw-1 检查到 10.0.1.2 的连通性并排查 OSPF 邻居问题",
     ["链路", "端口", "CRC", "丢包", "flapping", "OSPF", "光模块"]),
    ("stp_loop", "core-sw-1 的 CPU 占用率很高，接口 GE0/0/1 和 GE0/0/2 收发速率异常，网络时通时断，帮我排查是否环路",
     ["环路", "STP", "TCN", "广播", "CPU", "风暴"]),
    ("arp_poison", "核心交换机上 10.0.1.2 经常 ping 不通，接口都是 up 的，帮我排查 ARP 问题",
     ["ARP", "MAC", "冲突", "arp"]),
    ("bgp_flap", "core-rtr-1 的 BGP 邻居 10.0.1.1 一直处于 Active 状态，帮我排查原因",
     ["BGP", "Active", "邻居", "抖动"]),
    ("acl_deny", "从 core-sw-1 ping 10.0.1.2 全部超时但接口是 up 的，怀疑被 ACL 拦截，帮我确认并给出处置",
     ["ACL", "3001", "拒绝", "deny", "过滤"]),
]


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {extra}")


async def run_case(scenario, question, keywords, print_answer=False):
    print(f"\n== scenario={scenario} ==")
    print("Q:", question, flush=True)
    set_current_scenario(scenario)
    answer = ""
    tool_count = 0
    tool_names = []
    async for ev in run_agent(question, []):
        t = ev.get("type")
        if t == "tool":
            tool_count += 1
            tool_names.append(ev.get("tool"))
            cmd = ev.get("args") or {}
            cstr = cmd.get("command") or cmd.get("target") or str(cmd)[:80]
            print(f"  [tool#{tool_count}] {ev.get('tool')} ok={ev.get('ok')} :: {cstr}", flush=True)
        elif t == "delta":
            answer += ev.get("content", "")
        elif t == "error":
            print("  ERROR:", ev.get("message"), flush=True)
    check("至少调用 2 次工具", tool_count >= 2, f"tools={tool_names}")
    hits = [k for k in keywords if k in answer]
    check("答案命中场景特征", len(hits) >= 2, f"hits={hits} keywords={keywords}")
    print(f"  答案片段：{answer[:160].replace(chr(10), ' ')}", flush=True)
    if print_answer:
        print("  ===== 完整答案 =====\n" + answer + "\n  ===== 答案结束 =====", flush=True)
    return answer


async def main():
    # 支持只跑指定场景：python test_scenarios_agent.py acl_deny flapping
    only = [a.lower() for a in sys.argv[1:]]
    for scenario, question, keywords in CASES:
        if only and scenario not in only:
            continue
        try:
            await run_case(scenario, question, keywords, print_answer=scenario in only)
        except Exception as exc:  # noqa: BLE001
            global FAIL
            FAIL += 1
            print(f"  [FAIL] {scenario} 执行异常：{exc}")
    print(f"\n结果：{PASS} 通过，{FAIL} 失败")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())

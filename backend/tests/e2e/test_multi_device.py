# -*- coding: utf-8 -*-
"""优化4：Agent 多设备协同 + 时序推理 单元测试。

验证三层内容：
1. 多设备视角：每个故障场景在关联设备上有互相印证的异常输出（跨设备协同的数据基础）；
2. get_event_timeline：新工具输出时间升序的故障演进时间线（时序推理）；
3. 工具注册与 RBAC：get_event_timeline 已注册且 operator/admin 可用。
运行：cd backend; ..\\.venv\\Scripts\\python.exe -X utf8 tests\\test_multi_device.py
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.agent import devices as dev_mod  # noqa: E402
from app.agent.tools import ROLE_TOOLS, _HANDLERS  # noqa: E402

SCENARIOS = ["flapping", "stp_loop", "arp_poison", "bgp_flap", "acl_deny"]
PASS = 0
FAIL = 0


def _run(coro):
    return asyncio.run(coro)


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


def client_for(devname: str):
    dev = next(d for d in dev_mod.get_devices() if d.name == devname)
    return dev_mod.get_device_client(dev)


async def run_cmd(client, cmd: str) -> str:
    return await client.run(cmd)


def test_multi_device_perspective():
    print("== 多设备协同：各场景关联设备异常视角 ==")
    for sc in SCENARIOS:
        dev_mod.set_current_scenario(sc)

        async def probe():
            out = {}
            sw = client_for("core-sw-1")
            rtr = client_for("core-rtr-1")
            fw = client_for("fw-1")
            out["sw_if"] = await run_cmd(sw, "display interface brief")
            out["rtr_if"] = await run_cmd(rtr, "display interface brief")
            out["sw_arp"] = await run_cmd(sw, "display arp")
            out["rtr_arp"] = await run_cmd(rtr, "display arp")
            out["rtr_bgp"] = await run_cmd(rtr, "display bgp peer")
            out["sw_bgp"] = await run_cmd(sw, "display bgp peer")
            out["sw_acl"] = await run_cmd(sw, "display acl 3001")
            out["fw_tr"] = await run_cmd(fw, "tracert 10.0.1.2")
            return out

        o = _run(probe())

        if sc == "flapping":
            check(f"{sc}: 交换机侧 GE0/0/1 down", "GigabitEthernet0/0/1              down" in o["sw_if"], o["sw_if"][:80])
            check(f"{sc}: 路由器侧 GE0/0/0 down（跨设备印证）", "GigabitEthernet0/0/0              down" in o["rtr_if"], o["rtr_if"][:80])
        elif sc == "stp_loop":
            check(f"{sc}: 交换机侧接口高利用率", re.search(r"87\.3%", o["sw_if"]) is not None, o["sw_if"][:80])
            check(f"{sc}: 路由器对端接口高利用率（跨设备印证）", re.search(r"85\.9%", o["rtr_if"]) is not None, o["rtr_if"][:80])
        elif sc == "arp_poison":
            check(f"{sc}: 交换机侧 ARP 冲突", "MAC changed" in o["sw_arp"], o["sw_arp"][:80])
            check(f"{sc}: 路由器侧 ARP 异常（跨设备印证）", "MAC changed" in o["rtr_arp"], o["rtr_arp"][:80])
        elif sc == "bgp_flap":
            check(f"{sc}: 路由器侧 BGP Active/ConnectRetry", "BGP state = Active" in o["rtr_bgp"] and "ConnectRetry" in o["rtr_bgp"], o["rtr_bgp"][:80])
            check(f"{sc}: 交换机侧 BGP 同样 Active（跨设备印证）", "BGP state = Active" in o["sw_bgp"], o["sw_bgp"][:80])
        elif sc == "acl_deny":
            check(f"{sc}: 交换机侧 ACL deny 命中", "(12 times matched)" in o["sw_acl"], o["sw_acl"][:80])
            check(f"{sc}: 防火墙侧 tracert 全超时（跨设备印证）", o["fw_tr"].count("* * *") >= 3, o["fw_tr"][:80])


def test_event_timeline():
    print("== 时序推理：get_event_timeline 时间线 ==")
    for sc in SCENARIOS:
        dev_mod.set_current_scenario(sc)

        async def probe():
            sw = client_for("core-sw-1")
            return await run_cmd(sw, "display fault timeline")

        tl = _run(probe())
        check(f"{sc}: 输出含时间线标题", "Fault Timeline" in tl and sc in tl, tl[:60])
        # 提取时间戳并按升序校验
        ts = re.findall(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", tl)
        check(f"{sc}: 时间戳数量≥3", len(ts) >= 3, str(ts))
        if ts:
            check(f"{sc}: 时间戳升序（最早→最新）", ts == sorted(ts), f"{ts}")
    # 无关命令不触发时间线
    dev_mod.set_current_scenario("flapping")

    async def probe2():
        sw = client_for("core-sw-1")
        return await run_cmd(sw, "display version")

    v = _run(probe2())
    check("普通命令不受影响（无时间线输出）", "Fault Timeline" not in v)


def test_tool_registry():
    print("== 工具注册与 RBAC ==")
    check("get_event_timeline 已注册 handler", "get_event_timeline" in _HANDLERS)
    check("operator 可用 get_event_timeline", "get_event_timeline" in ROLE_TOOLS["operator"])
    check("admin 可用 get_event_timeline", "get_event_timeline" in ROLE_TOOLS["admin"])
    check("viewer 不可用设备工具", "get_event_timeline" not in ROLE_TOOLS["viewer"])


if __name__ == "__main__":
    test_tool_registry()
    test_event_timeline()
    test_multi_device_perspective()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)

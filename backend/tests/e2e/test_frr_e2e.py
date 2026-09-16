# -*- coding: utf-8 -*-
"""方案 B · FRR 真实协议栈端到端验证（Docker 引擎就绪后运行）。

用法：
    cd backend
    ..\.venv\Scripts\python.exe -X utf8 tests\test_frr_e2e.py

覆盖：
  1) 真实 OSPF 建邻：frr1 <-> frr2 应为 FULL/DR（vtysh show ip ospf neighbor）
  2) 真实 eBGP 建邻：frr2 <-> frr3 应为 Established（show bgp summary）
  3) 真实路由表：frr1 应通过 OSPF 学到 10.0.23.0/29（show ip route）
  4) 命令翻译层：华为 display 风格 → FRR show 命令
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

from app.agent.devices import Device, NetmikoDevice

PASS = 0
FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {extra}")


def frr_dev(name: str, port: int) -> Device:
    return Device(name=name, host="127.0.0.1", port=port, device_type="frr",
                  username="admin", password="admin123", role="router")


async def run_cmd(dev: Device, cmd: str) -> str:
    client = NetmikoDevice(dev)
    return await client.run(cmd)


async def main():
    # 0) 命令翻译层单测
    tr = NetmikoDevice._frr_command
    check("翻译: display ospf peer", tr("display ospf peer") == "show ip ospf neighbor")
    check("翻译: display bgp peer", tr("display bgp peer") == "show bgp summary")
    check("翻译: display ip routing-table", tr("display ip routing-table") == "show ip route")
    check("翻译兜底: display version", tr("display version") == "show version")

    # 1) OSPF 建邻（frr1 ↔ frr2）
    print("== OSPF ==")
    try:
        out1 = await run_cmd(frr_dev("frr1", 2201), "display ospf peer")
        print(out1[:400])
        check("frr1 能看到 frr2 邻居", "10.0.12.3" in out1 and "Full" in out1, out1[-200:])
    except Exception as e:
        check("frr1 OSPF 查询", False, f"ERR {type(e).__name__}: {str(e)[:150]}")

    # 2) eBGP 建邻（frr2 ↔ frr3）
    print("== BGP ==")
    try:
        out3 = await run_cmd(frr_dev("frr3", 2203), "display bgp peer")
        print(out3[:400])
        check("frr3 BGP 邻居 Established（前缀已交换）", "10.0.23.2" in out3 and "(Policy)" not in out3, out3[-200:])
    except Exception as e:
        check("frr3 BGP 查询", False, f"ERR {type(e).__name__}: {str(e)[:150]}")

    # 3) 路由表：frr1 通过 OSPF 学到远端网段
    print("== ROUTE ==")
    try:
        outr = await run_cmd(frr_dev("frr1", 2201), "display ip routing-table")
        check("frr1 学到 10.0.23.0/29（OSPF）", "10.0.23.0/29" in outr, outr[-250:])
        check("frr1 学到 2.2.2.2/32（OSPF 环回）", "2.2.2.2/32" in outr, outr[-250:])
    except Exception as e:
        check("frr1 路由表", False, f"ERR {type(e).__name__}: {str(e)[:150]}")

    print(f"\n结果：{PASS} 通过，{FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())

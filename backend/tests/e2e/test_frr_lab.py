# -*- coding: utf-8 -*-
"""FRR 真实实验室端到端测试：故障注入 → 状态变化 → 恢复 → 状态复原。

覆盖 3 类可逆故障（真实 vtysh 配置操作，走 Netmiko SSH）：
  1. link_down        frr1 eth0  接口 shutdown → OSPF 邻居消失 → 恢复后 Full/DR
  2. bgp_neighbor_down frr3 eth0  BGP 邻居 shutdown → eBGP Idle → 恢复后 Established
  3. ospf_cost        frr2 eth0  OSPF cost 调大 → 生效 → 恢复后默认

运行（backend 目录，需 FRR 容器栈已启动）：
  ..\\.venv\\Scripts\\python.exe -X utf8 tests\\test_frr_lab.py
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.devices import get_devices  # noqa: E402
from app.agent.frr_lab import FrrLab  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


async def wait_for(pred, timeout: float, interval: float = 5.0) -> bool:
    """轮询直到 pred() 为 True 或超时。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if await pred():
            return True
        await asyncio.sleep(interval)
    return await pred()


def _has_ospf_peer(out: str, peer_id: str = "2.2.2.2") -> bool:
    return peer_id in out and "Full" in out


def _bgp_state(out: str, peer: str = "10.0.23.2") -> str:
    """从 show bgp summary 提取对端 State/PfxRcd；找不到返回 'missing'。"""
    for line in out.splitlines():
        if line.strip().startswith(peer):
            parts = line.split()
            return parts[-3] if len(parts) >= 7 else "unknown"
    return "missing"


async def main() -> int:
    devs = {d.name: d for d in get_devices() if d.device_type == "frr"}
    for name in ("frr1", "frr2", "frr3"):
        if name not in devs:
            print(f"[SKIP] {name} 未在设备清单中（DEVICE_MODE 需为 real）")
            return 1
    lab1, lab2, lab3 = FrrLab(devs["frr1"]), FrrLab(devs["frr2"]), FrrLab(devs["frr3"])

    # ---------------------------------------------------------- 0. 自愈基线
    # 先幂等恢复所有合法故障组合（上次崩溃残留的 shutdown/cost 也会被清掉），再等收敛
    print("== 自愈：清残留故障 ==")
    for lab, fault, iface in (
        (lab1, "link_down", "eth0"),
        (lab1, "ospf_cost", "eth0"),
        (lab2, "link_down", "eth0"),
        (lab2, "ospf_cost", "eth0"),
        (lab2, "bgp_neighbor_down", "eth1"),
        (lab3, "link_down", "eth0"),
        (lab3, "bgp_neighbor_down", "eth0"),
    ):
        try:
            await lab.recover(fault, iface)
        except Exception:  # noqa: BLE001（未注入时 recover 也幂等无害）
            pass
    await asyncio.sleep(20)  # 等 OSPF/BGP 收敛

    # ---------------------------------------------------------- 基线
    print("== 基线状态 ==")
    base1 = await lab1._run('vtysh -c "show ip ospf neighbor"')
    base3 = await lab3._run('vtysh -c "show bgp summary"')
    check("基线：frr1 有 OSPF 邻居 Full/DR", _has_ospf_peer(base1))
    check("基线：frr3 eBGP 已建立（PfxRcd=2）", _bgp_state(base3) == "2", f"state={_bgp_state(base3)}")
    if not all(ok for _, ok, _ in RESULTS):
        print("基线异常，中止测试（请确认 FRR 容器栈已启动且 8/8 基线通过）")
        return 1

    # ---------------------------------------------------------- 1. link_down
    print("== 用例1：link_down frr1 eth0（OSPF 链路断开）==")
    out = await lab1.inject("link_down", "eth0")
    check("注入成功（vtysh 无报错）", "shutdown" in out.lower() or "configuration" in out.lower(), out.splitlines()[-1][:80])

    async def _ospf_down() -> bool:
        return not _has_ospf_peer(await lab1._run('vtysh -c "show ip ospf neighbor"'))

    ok_down = await wait_for(_ospf_down, timeout=60)
    check("注入后：frr1 的 2.2.2.2 邻居消失/非 Full", ok_down)

    out = await lab1.recover("link_down", "eth0")

    async def _ospf_up() -> bool:
        return _has_ospf_peer(await lab1._run('vtysh -c "show ip ospf neighbor"'))

    ok_up = await wait_for(_ospf_up, timeout=90)
    check("恢复后：frr1 OSPF 邻居回到 Full/DR", ok_up)

    # ---------------------------------------------------------- 2. bgp_neighbor_down
    print("== 用例2：bgp_neighbor_down frr3（eBGP 会话中断）==")
    await lab3.inject("bgp_neighbor_down", "eth0")

    async def _bgp_not_est() -> bool:
        return _bgp_state(await lab3._run('vtysh -c "show bgp summary"')) != "2"

    ok_idle = await wait_for(_bgp_not_est, timeout=30, interval=3)
    check("注入后：frr3 eBGP 非 Established", ok_idle, f"state={_bgp_state(await lab3._run('vtysh -c \"show bgp summary\"'))}")
    await lab3.recover("bgp_neighbor_down", "eth0")

    async def _bgp_est() -> bool:
        return _bgp_state(await lab3._run('vtysh -c "show bgp summary"')) == "2"

    ok_est = await wait_for(_bgp_est, timeout=60, interval=5)
    check("恢复后：frr3 eBGP 回到 Established（PfxRcd=2）", ok_est)

    # ---------------------------------------------------------- 3. ospf_cost
    print("== 用例3：ospf_cost frr2 eth0（路径劣化）==")
    await lab2.inject("ospf_cost", "eth0")
    cost_out = await lab2._run('vtysh -c "show ip ospf interface eth0"')
    check("注入后：eth0 接口 cost=10000 生效", "Cost: 10000" in cost_out)
    await lab2.recover("ospf_cost", "eth0")
    cost_out2 = await lab2._run('vtysh -c "show ip ospf interface eth0"')
    check("恢复后：eth0 接口 cost 回默认（非 10000）", "Cost: 10000" not in cost_out2 and "Cost: 10" in cost_out2)

    # ---------------------------------------------------------- 汇总
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    print(f"\n结果：{passed} 通过，{failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

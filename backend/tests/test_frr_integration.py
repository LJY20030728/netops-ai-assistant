# -*- coding: utf-8 -*-
"""FRR 真实实验室集成测试（pytest）。

覆盖"故障注入 → 真实协议状态变化 → 恢复 → 状态复原"闭环：
  1. ospf_cost         frr2 eth0  cost 10000 生效 → 恢复回默认 cost
  2. link_down         frr1 eth0  OSPF 邻居消失 → 恢复后 Full
  3. bgp_neighbor_down frr3 eth0  eBGP Idle → 恢复后 Established

运行前提：Docker Desktop 在线，且 frr1/frr2/frr3 容器正在运行
（docker compose -f docker-compose.frr.yml up -d）。
不满足时自动 skip，不影响单元测试全绿。

设计要点：
- 不调用 LLM、不花钱；
- 每个用例 try/finally 保证故障恢复（测试崩溃也不污染实验环境）；
- wait_for 轮询真实 vtysh 输出（OSPF Full / BGP PfxRcd），不是 mock。
"""
import asyncio
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from app.agent.devices import find_device
from app.agent.frr_lab import FrrLab


# ---------------------------------------------------------------- 环境探测
def _docker_cli() -> str | None:
    return shutil.which("docker")


def _running_containers() -> set[str]:
    cli = _docker_cli()
    if not cli:
        return set()
    r = subprocess.run([cli, "ps", "--format", "{{.Names}}"],
                       capture_output=True, text=True, timeout=15)
    return set(r.stdout.split())


def _require_frr_stack():
    """pytest 前置：docker 在线且三个 FRR 容器都在跑。"""
    cli = _docker_cli()
    if not cli:
        pytest.skip("docker CLI 不可用（未安装 Docker Desktop）")
    running = _running_containers()
    missing = {"frr1", "frr2", "frr3"} - running
    if missing:
        pytest.skip(f"FRR 容器未全部运行，缺：{sorted(missing)}（docker compose -f docker-compose.frr.yml up -d）")
    for name in ("frr1", "frr2", "frr3"):
        if find_device(name) is None:
            pytest.skip(f"devices.json 未配置 {name}")


async def wait_for(pred, timeout: float, interval: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if await pred():
            return True
        await asyncio.sleep(interval)
    return await pred()


# ---------------------------------------------------------------- 解析辅助
def _ospf_full(out: str, peer: str = "2.2.2.2") -> bool:
    return peer in out and "Full" in out


def _bgp_pfxrcd(out: str, peer: str = "10.0.23.2") -> str:
    for line in out.splitlines():
        if line.strip().startswith(peer):
            parts = line.split()
            return parts[-3] if len(parts) >= 7 else "unknown"
    return "missing"


# ---------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def labs():
    _require_frr_stack()
    l1, l2, l3 = FrrLab(find_device("frr1")), FrrLab(find_device("frr2")), FrrLab(find_device("frr3"))
    # 自愈：清掉上次测试残留的 shutdown / cost
    async def _selfheal():
        for lab, fault, iface in (
            (l1, "link_down", "eth0"), (l1, "ospf_cost", "eth0"),
            (l2, "link_down", "eth0"), (l2, "ospf_cost", "eth0"), (l2, "bgp_neighbor_down", "eth1"),
            (l3, "link_down", "eth0"), (l3, "bgp_neighbor_down", "eth0"),
        ):
            try:
                await lab.recover(fault, iface)
            except Exception:  # noqa: BLE001
                pass
        await asyncio.sleep(20)  # 等 OSPF/BGP 收敛到基线
    asyncio.run(_selfheal())
    return l1, l2, l3


# ---------------------------------------------------------------- 用例
@pytest.mark.dock
(labs):
    """frr2 eth0 注入 ospf_cost=10000 → vtysh 可见 Cost: 10000 → 恢复后回默认。"""
    _, lab2, _ = labs

    async def _body():
        try:
            await lab2.inject("ospf_cost", "eth0")
            after = await lab2._run('vtysh -c "show ip ospf interface eth0"')
            assert "Cost: 10000" in after, f"注入后未生效:\n{after}"
        finally:
            await lab2.recover("ospf_cost", "eth0")
        restored = await lab2._run('vtysh -c "show ip ospf interface eth0"')
        assert "Cost: 10000" not in restored, f"恢复后 cost 仍为 10000:\n{restored}"
        assert "Cost: 10" in restored, f"未观察到默认 cost:\n{restored}"

    asyncio.run(_body())


@pytest.mark.dock
(labs):
    """frr1 eth0 shutdown → OSPF 邻居从 Full 消失 → no shutdown 后回到 Full。"""
    lab1, _, _ = labs

    async def _body():
        base = await lab1._run('vtysh -c "show ip ospf neighbor"')
        assert _ospf_full(base), f"基线异常：frr1 无 Full OSPF 邻居:\n{base}"
        try:
            await lab1.inject("link_down", "eth0")

            async def _down() -> bool:
                return not _ospf_full(await lab1._run('vtysh -c "show ip ospf neighbor"'))

            ok_down = await wait_for(_down, timeout=60)
            assert ok_down, "注入 link_down 后 60s 内 OSPF 邻居未消失"
        finally:
            await lab1.recover("link_down", "eth0")

        async def _up() -> bool:
            return _ospf_full(await lab1._run('vtysh -c "show ip ospf neighbor"'))

        ok_up = await wait_for(_up, timeout=90)
        assert ok_up, "恢复 link_down 后 90s 内 OSPF 邻居未回到 Full"

    asyncio.run(_body())


@pytest.mark.dock
(labs):
    """frr3 BGP 邻居 shutdown → eBGP 会话非 Established → 恢复后 PfxRcd=2。"""
    _, _, lab3 = labs

    async def _body():
        base = await lab3._run('vtysh -c "show bgp summary"')
        assert _bgp_pfxrcd(base) == "2", f"基线异常：frr3 eBGP 未 Established:\n{base}"
        try:
            await lab3.inject("bgp_neighbor_down", "eth0")

            async def _down() -> bool:
                return _bgp_pfxrcd(await lab3._run('vtysh -c "show bgp summary"')) != "2"

            ok_down = await wait_for(_down, timeout=30, interval=3)
            assert ok_down, "注入 bgp_neighbor_down 后 30s 内 eBGP 未脱离 Established"
        finally:
            await lab3.recover("bgp_neighbor_down", "eth0")

        async def _up() -> bool:
            return _bgp_pfxrcd(await lab3._run('vtysh -c "show bgp summary"')) == "2"

        ok_up = await wait_for(_up, timeout=60, interval=5)
        assert ok_up, "恢复 bgp_neighbor_down 后 60s 内 eBGP 未回到 Established"

    asyncio.run(_body())

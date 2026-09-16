"""FRR 真实实验室（方案 B 排障演练）：故障注入 / 恢复 / 状态读取。

设计原则：
- **双通道运维模型**（真实网络运维实践）：
  * 前台管理通道 = Netmiko SSH（Agent 的 run_device_command 读取状态，见 devices.py）；
  * 带外管理通道（Out-of-Band）= docker exec 直入容器 vtysh，类比机房 console/ILO——
    用于**会切断管理链路本身的故障**（如 shutdown eth0 会同时切断 SSH 通道，此时只能带外恢复）；
- 所有故障**可逆**：recover = apply 的逆命令序列；注入前自动记录现状，恢复后返回验证输出；
- 支持注入后状态验证（verify），供测试与 Agent 取证闭环使用。
"""
import asyncio
import shutil
import subprocess
from pathlib import Path

from app.agent.devices import Device, DeviceError

# 本机 docker CLI 候选路径（Windows Docker Desktop 非默认路径 / 类 Unix 默认路径）
_DOCKER_CANDIDATES = (
    r"C:\Users\Curry\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe",
    "/usr/bin/docker",
    "/usr/local/bin/docker",
    "/opt/homebrew/bin/docker",
)


def _find_docker() -> str:
    found = shutil.which("docker")
    if found:
        return found
    for cand in _DOCKER_CANDIDATES:
        if Path(cand).exists():
            return cand
    raise DeviceError("未找到 docker CLI，无法执行带外故障注入（需 Docker Desktop 已安装）")

# 每台 FRR 设备的 BGP 事实（用于 bgp_neighbor_down 的 local-as / peer 推导）
_BGP_FACTS = {
    "frr2": {"local_as": 65002, "peer_ip": "10.0.23.3"},
    "frr3": {"local_as": 65003, "peer_ip": "10.0.23.2"},
}

# 故障目录：apply=注入命令序列（列表按序执行为一条 vtysh -c 链）、
# recover=恢复命令序列、verify=注入后验证命令（返回给调用方 / 测试断言）。
# 占位符 {iface}/{local_as}/{peer_ip} 由 FrrLab 按设备事实填充。
FAULTS: dict[str, dict] = {
    "link_down": {
        "label": "接口 shutdown（物理链路断开）",
        "apply": ["conf t", "interface {iface}", "shutdown"],
        "recover": ["conf t", "interface {iface}", "no shutdown"],
        "verify": "show interface {iface}",
        "impact": "该接口对应的 OSPF/eBGP 邻居将 down，路由被撤销",
    },
    "ospf_cost": {
        "label": "接口 OSPF cost 调大（路由路径劣化）",
        "apply": ["conf t", "interface {iface}", "ip ospf cost 10000"],
        "recover": ["conf t", "interface {iface}", "no ip ospf cost"],
        "verify": "show ip ospf interface {iface}",
        "impact": "OSPF 将该接口视为高成本路径，SPF 可能切换下一跳",
    },
    "bgp_neighbor_down": {
        "label": "BGP 邻居 shutdown（eBGP 会话中断）",
        "apply": ["conf t", "router bgp {local_as}", "neighbor {peer_ip} shutdown"],
        "recover": ["conf t", "router bgp {local_as}", "no neighbor {peer_ip} shutdown"],
        "verify": "show bgp summary",
        "impact": "eBGP 会话转为 Idle，前缀停止交换（本设备为 bgp 设备才可用）",
    },
}

_LEGAL: dict[str, dict[str, str]] = {
    "frr1": {"link_down": "eth0", "ospf_cost": "eth0"},
    "frr2": {"link_down": "eth0", "ospf_cost": "eth0", "bgp_neighbor_down": "eth1"},
    "frr3": {"link_down": "eth0", "bgp_neighbor_down": "eth0"},
}


class FrrLab:
    """对单台 FRR 设备执行故障注入/恢复/验证（真实 SSH→vtysh）。"""

    def __init__(self, device: Device):
        if device.device_type != "frr":
            raise DeviceError(f"{device.name} 不是 FRR 设备，无法执行真实故障注入")
        self.device = device

    # ------------------------------------------------------------- 带外执行
    async def _run(self, cmd: str) -> str:
        """docker exec 直入容器执行 vtysh 命令（带外通道，链路故障不切断）。

        cmd 若未带 vtysh 前缀（如 verify 的 'show ...'），自动包成 vtysh -c，
        避免被容器 shell 当成独立命令执行（sh: show: not found）。
        """
        docker = _find_docker()
        if not cmd.strip().startswith("vtysh"):
            cmd = f'vtysh -c "{cmd}"'
        argv = [docker, "exec", self.device.name, "sh", "-c", cmd]

        def _do() -> str:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
            out = (proc.stdout or "").strip() + (("\n" + proc.stderr.strip()) if proc.stderr and proc.stderr.strip() else "")
            if proc.returncode != 0 and not out:
                raise DeviceError(f"docker exec 失败（rc={proc.returncode}）：{proc.stderr[:300]}")
            return out

        return await asyncio.to_thread(_do)

    def _vtysh(self, cmds: list[str]) -> str:
        """把命令序列拼成一条 vtysh -c 链（每条 -c 独立进入对应模式）。"""
        quoted = " ".join(f'-c "{c}"' for c in cmds)
        return f"vtysh {quoted}"

    # ------------------------------------------------------------- 故障操作
    def _fill(self, fault_cfg: dict, iface: str) -> dict:
        bgp = _BGP_FACTS.get(self.device.name, {})
        d = dict(fault_cfg)
        d["apply"] = [c.format(iface=iface, local_as=bgp.get("local_as", ""), peer_ip=bgp.get("peer_ip", "")) for c in d["apply"]]
        d["recover"] = [c.format(iface=iface, local_as=bgp.get("local_as", ""), peer_ip=bgp.get("peer_ip", "")) for c in d["recover"]]
        d["verify"] = d["verify"].format(iface=iface)
        return d

    async def inject(self, fault: str, iface: str) -> str:
        """注入故障：执行 apply 命令链，返回 verify 输出。"""
        cfg = self._resolve(fault, iface)
        out = await self._run(self._vtysh(cfg["apply"]))
        return f"[FRR:{self.device.name}] 注入故障「{cfg['label']}」({iface})\n{out}\n--- 验证 ---\n{await self._run(cfg['verify'])}"

    async def recover(self, fault: str, iface: str) -> str:
        """恢复故障：执行 recover 命令链，返回 verify 输出。"""
        cfg = self._resolve(fault, iface)
        out = await self._run(self._vtysh(cfg["recover"]))
        return f"[FRR:{self.device.name}] 恢复故障「{cfg['label']}」({iface})\n{out}\n--- 验证 ---\n{await self._run(cfg['verify'])}"

    async def status(self, fault: str, iface: str) -> str:
        """读取当前故障相关状态（不做任何修改）。"""
        cfg = self._resolve(fault, iface)
        return f"[FRR:{self.device.name}] 状态（{cfg['label']}）\n{await self._run(cfg['verify'])}"

    def _resolve(self, fault: str, iface: str) -> dict:
        if fault not in FAULTS:
            raise DeviceError(f"未知故障：{fault}。可用：{', '.join(FAULTS)}")
        legal = _LEGAL.get(self.device.name, {})
        if fault not in legal:
            raise DeviceError(f"{self.device.name} 不支持故障 {fault}（仅支持：{', '.join(legal) or '无'}）")
        if iface != legal[fault]:
            raise DeviceError(f"{self.device.name} 的 {fault} 故障仅支持接口 {legal[fault]}（当前传入 {iface}）")
        return self._fill(FAULTS[fault], iface)

    async def status_all(self) -> dict:
        """读取设备当前核心状态（OSPF 邻居 + BGP 摘要 + 路由表），供拓扑页使用。"""
        if self.device.name == "frr1":
            cmds = ["show ip ospf neighbor", "show ip route"]
        elif self.device.name == "frr2":
            cmds = ["show ip ospf neighbor", "show bgp summary"]
        else:
            cmds = ["show bgp summary"]
        outputs: dict[str, str] = {}
        for frr_cmd in cmds:
            try:
                outputs[frr_cmd] = await self._run(f'vtysh -c "{frr_cmd}"')
            except Exception as exc:  # noqa: BLE001
                outputs[frr_cmd] = f"<读取失败: {exc}>"
        return {
            "device": self.device.name,
            "role": self.device.role,
            "outputs": outputs,
            "parsed": _parse_status(self.device.name, outputs),
        }


# ---------------------------------------------------------------- 状态解析
_OSPF_HEADER_SKIP = {"neighbor", "total", "number", "address", "state", "interface", "displayed", "==="}


def _parse_ospf(output: str) -> list[dict]:
    """解析 show ip ospf neighbor → [{id, state, address}]。"""
    peers: list[dict] = []
    for line in (output or "").splitlines():
        line = line.strip()
        if not line or line.startswith("Neighbor ID") or not line[0].isdigit():
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        nid, _pri, state = parts[0], parts[1], parts[2]
        address = parts[5] if "." in parts[5] else (parts[6] if len(parts) > 6 and "." in parts[6] else "")
        peers.append({"id": nid, "state": state, "address": address})
    return peers


def _parse_bgp(output: str) -> list[dict]:
    """解析 show bgp summary → [{peer, as, state}]；state 为数字=已建立，否则为字面状态。"""
    peers: list[dict] = []
    for line in (output or "").splitlines():
        line = line.strip()
        if not line or line.startswith("Neighbor") or line.startswith("Total") or line.startswith("=") or line.startswith("BGP"):
            continue
        parts = line.split()
        if len(parts) < 7 or "." not in parts[0]:
            continue
        peer, asn = parts[0], parts[2]
        state = parts[-3]  # State/PfxRcd 列（数字=已建立；字面值=异常）
        peers.append({"peer": peer, "as": asn, "state": state})
    return peers


def _parse_routes(output: str) -> list[str]:
    """解析 show ip route → 路由条目（O=OSPF/B=BGP/C=直连/K=内核）。"""
    routes: list[str] = []
    for line in (output or "").splitlines():
        line = line.strip()
        if not line or line.startswith("Codes") or line.startswith("==="):
            continue
        if len(line) > 4 and line[1] in "OKC>*" and "/" in line:
            routes.append(line)
    return routes[:12]


def _parse_status(device: str, outputs: dict[str, str]) -> dict:
    parsed: dict = {"ospf_peers": [], "bgp_peers": [], "routes": []}
    for cmd, out in outputs.items():
        if "ospf neighbor" in cmd:
            parsed["ospf_peers"] = _parse_ospf(out)
        elif "bgp summary" in cmd:
            parsed["bgp_peers"] = _parse_bgp(out)
        elif "ip route" in cmd:
            parsed["routes"] = _parse_routes(out)
    # 健康度契约：真实 FRR 设备必须具备"关键邻居"（OSPF 或 BGP 且状态正常）。
    # 直连路由不参与判定——eth0 shutdown 后直连路由仍在，会掩盖故障（实测教训）。
    def _abnormal(state: str) -> bool:
        s = state.split("/")[0].lower()
        return any(k in s for k in ("down", "exstart", "policy", "idle", "active", "attempt", "shut"))

    peers = parsed["ospf_peers"] + parsed["bgp_peers"]
    if not peers and not parsed["routes"]:
        parsed["healthy"] = None  # 未知
    elif not peers:
        parsed["healthy"] = False  # 设备活着但关键邻居全丢 → 故障态（如 link_down 后 OSPF 邻居消失）
    else:
        parsed["healthy"] = all(not _abnormal(p["state"]) for p in peers)
    return parsed

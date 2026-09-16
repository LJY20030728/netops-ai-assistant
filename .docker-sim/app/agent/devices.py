"""设备接入层：设备清单 + 两种连接方式（仿真 / Netmiko 真实连接）。

- device_mode=simulate（默认）：内置仿真设备，返回确定性、可诊断的模拟输出，
  无需真实设备即可演示 Agent 工具调用全链路。输出标注为仿真，不得当作真实数据。
- device_mode=real：通过 Netmiko SSH 连接 EVE-NG 仿真设备执行命令。

设备清单见 backend/devices.json（默认账号仅用于本地仿真实验室，勿用于生产）。
"""
import asyncio
import json
import threading
from dataclasses import dataclass, field

from app.config import DEVICES_FILE, settings


@dataclass
class Device:
    name: str
    host: str
    port: int
    device_type: str
    username: str
    password: str
    role: str = ""
    note: str = ""
    extra: dict = field(default_factory=dict)


def _load_devices() -> list[Device]:
    if not DEVICES_FILE.exists():
        return []
    data = json.loads(DEVICES_FILE.read_text(encoding="utf-8"))
    return [Device(**d) for d in data.get("devices", [])]


def get_devices() -> list[Device]:
    return _load_devices()


def find_device(name: str) -> Device | None:
    name = (name or "").strip().lower()
    for d in _load_devices():
        if d.name.lower() == name:
            return d
    # 模糊匹配：包含关系
    for d in _load_devices():
        if name and name in d.name.lower():
            return d
    return None


class DeviceError(RuntimeError):
    pass


# ---------------------------------------------------------------- 仿真设备
# 故障场景库：simulate 模式下可运行多个自洽的故障剧本，用于演示 Agent 取证推理。
# 每个场景下各命令输出互相印证（接口/协议邻居/日志/连通性/配置一致）。
VALID_SCENARIOS = ["flapping", "stp_loop", "arp_poison", "bgp_flap", "acl_deny"]

_scenario_lock = threading.Lock()
_current_scenario: str = settings.sim_fault_scenario


def get_current_scenario() -> str:
    return _current_scenario


def set_current_scenario(name: str) -> str:
    """运行时切换仿真故障场景（仅 simulate 模式有意义）。"""
    global _current_scenario
    name = (name or "").strip().lower()
    if name not in VALID_SCENARIOS:
        raise DeviceError(f"未知仿真场景：{name}。可用：{', '.join(VALID_SCENARIOS)}")
    with _scenario_lock:
        _current_scenario = name
    return _current_scenario


class SimulatedDevice:
    """内置仿真设备：按当前故障场景返回一组自洽、可诊断的模拟输出。

    场景（core-sw-1 <-> core-rtr-1 互联，fw-1 旁路）：
    - flapping   ：互联链路质量差 → GE0/0/1 反复 up/down + CRC 增长 + OSPF 邻居间歇 Down + ping 75% 丢包；
    - stp_loop   ：二层环路 → STP TCN 频繁 + 广播风暴（接口 up 但利用率/CPU 飙升）+ ping 50% 丢包；
    - arp_poison ：ARP 表项异常 → 10.0.1.2 指向错误 MAC + ARP 冲突日志 + ping 间歇不通（物理正常）；
    - bgp_flap   ：BGP 邻居 Active 抖动 → 物理链路正常（ping 0% 丢包）但 BGP 邻居反复 down；
    - acl_deny   ：ACL 策略拦截 → 接口 up 但 ping 100% 超时 + ACL 匹配计数增长。
    所有输出均为仿真示例，用于演示 Agent 工具调用流程，不得当作真实数据。
    """

    def __init__(self, device: Device):
        self.device = device
        self._scenario = get_current_scenario()

    # -- 设备身份 --
    @property
    def _identity(self) -> str:
        return {
            "core-sw-1": "Huawei S5735-L24T4X 核心交换机",
            "core-rtr-1": "Huawei AR2220 核心路由器",
            "fw-1": "Huawei USG6300 防火墙",
        }.get(self.device.name, f"Huawei 设备（{self.device.name}）")

    # -- 命令分发 --
    async def run(self, command: str) -> str:
        cmd = (command or "").strip().lower()
        if not cmd:
            return "Error: empty command"

        # 设备名无关的通用命令
        if "display version" in cmd:
            return self._cmd_version()
        if "display device" in cmd:
            return self._cmd_device()
        if "display ntp" in cmd:
            return self._cmd_ntp()
        if "display cpu-usage" in cmd:
            return self._cmd_cpu_usage()
        if "display bgp peer" in cmd or "display bgp vpnv4" in cmd:
            return self._cmd_bgp_peer()
        if "display bgp summary" in cmd:
            return self._cmd_bgp_peer()
        if "display acl" in cmd:
            return self._cmd_acl()
        if "display traffic-filter" in cmd:
            return self._cmd_traffic_filter()
        if "display interface brief" in cmd:
            return self._cmd_interface_brief()
        if "display ip interface brief" in cmd:
            return self._cmd_ip_interface_brief()
        if "display ospf peer" in cmd:
            return self._cmd_ospf_peer()
        if "display ospf interface" in cmd:
            return self._cmd_ospf_interface()
        if "display arp" in cmd:
            return self._cmd_arp()
        if "display stp brief" in cmd or "display stp vlan" in cmd:
            return self._cmd_stp()
        if "display logbuffer" in cmd:
            return self._cmd_logbuffer()
        if "display current-configuration" in cmd:
            return self._cmd_current_config()

        # 接口详情（含具体端口）
        if "display interface" in cmd:
            return self._cmd_interface_detail(cmd)

        # ping / tracert
        if cmd.startswith("ping") or " ping " in cmd:
            return self._cmd_ping(cmd)
        if cmd.startswith("tracert") or cmd.startswith("traceroute") or " tracert " in cmd:
            return self._cmd_tracert(cmd)

        return f"Error: Unrecognized command '{command}'"

    def _cmd_version(self) -> str:
        return (
            f"{self._identity}\n"
            "Huawei Versatile Routing Platform Software\n"
            "VRP (R) software, Version 5.170 (S5735 V200R019C10SPC800)\n"
            "uptime is 42 days, 7 hours, 13 minutes\n"
        )

    def _cmd_interface_brief(self) -> str:
        if self.device.name == "core-sw-1":
            if self._scenario == "stp_loop":
                return (
                    "Interface                         PHY   Protocol  InUti OutUti   inErrors  CRC  Up/Down\n"
                    "GigabitEthernet0/0/1              up    up       87.3%  86.1%     15,238    0   0\n"
                    "GigabitEthernet0/0/2              up    up       79.8%  78.2%     12,904    0   0\n"
                    "GigabitEthernet0/0/3              up    up        0.3%   0.2%          0    0   0\n"
                    "GigabitEthernet0/0/24             up    up        2.1%   1.8%          0    0   0\n"
                    "Vlanif1                           up    up          -      -            -    -   -\n"
                )
            if self._scenario == "flapping":
                return (
                    "Interface                         PHY   Protocol  InUti OutUti   inErrors  CRC  Up/Down\n"
                    "GigabitEthernet0/0/1              down  down        0.1%   0.1%      1,024  512  42\n"
                    "GigabitEthernet0/0/2              up    up          0.8%   0.5%          0    0   0\n"
                    "GigabitEthernet0/0/3              up    up          0.3%   0.2%          0    0   0\n"
                    "GigabitEthernet0/0/24             up    up          2.1%   1.8%          0    0   0\n"
                    "Vlanif1                           up    up          -      -            -    -   -\n"
                )
            return (
                "Interface                         PHY   Protocol  InUti OutUti   inErrors  CRC  Up/Down\n"
                "GigabitEthernet0/0/1              up    up          0.4%   0.3%          0    0   0\n"
                "GigabitEthernet0/0/2              up    up          0.8%   0.5%          0    0   0\n"
                "GigabitEthernet0/0/3              up    up          0.3%   0.2%          0    0   0\n"
                "GigabitEthernet0/0/24             up    up          2.1%   1.8%          0    0   0\n"
                "Vlanif1                           up    up          -      -            -    -   -\n"
            )
        if self.device.name == "core-rtr-1":
            if self._scenario == "flapping":
                return (
                    "Interface                         PHY   Protocol  InUti OutUti   inErrors  CRC  Up/Down\n"
                    "GigabitEthernet0/0/0              down  down        0.1%   0.1%        823  401  40\n"
                    "GigabitEthernet0/0/1              up    up          1.2%   0.9%          0    0   0\n"
                    "GigabitEthernet0/0/2              up    up          0.4%   0.3%          0    0   0\n"
                )
            if self._scenario == "stp_loop":
                return (
                    "Interface                         PHY   Protocol  InUti OutUti   inErrors  CRC  Up/Down\n"
                    "GigabitEthernet0/0/0              up    up       85.9%  84.4%     13,501    0   0\n"
                    "GigabitEthernet0/0/1              up    up        1.2%   0.9%          0    0   0\n"
                    "GigabitEthernet0/0/2              up    up        0.4%   0.3%          0    0   0\n"
                )
            return (
                "Interface                         PHY   Protocol  InUti OutUti   inErrors  CRC  Up/Down\n"
                "GigabitEthernet0/0/0              up    up          0.4%   0.3%          0    0   0\n"
                "GigabitEthernet0/0/1              up    up          1.2%   0.9%          0    0   0\n"
                "GigabitEthernet0/0/2              up    up          0.4%   0.3%          0    0   0\n"
            )
        return (
            "Interface                         PHY   Protocol  InUti OutUti   inErrors  CRC  Up/Down\n"
            "GigabitEthernet1/0/0               up    up          0.2%   0.1%          0    0   0\n"
            "GigabitEthernet1/0/1               up    up          0.5%   0.4%          0    0   0\n"
        )

    def _cmd_ip_interface_brief(self) -> str:
        link_down = self._scenario == "flapping"
        if self.device.name == "core-sw-1":
            return (
                "*down: administratively down\n"
                "Interface                         IP Address/Mask      Physical   Protocol\n"
                f"GigabitEthernet0/0/1              unassigned            {'down' if link_down else 'up'}         {'down' if link_down else 'up'}\n"
                "Vlanif1                           10.0.1.1/24           up         up\n"
            )
        if self.device.name == "core-rtr-1":
            return (
                "*down: administratively down\n"
                "Interface                         IP Address/Mask      Physical   Protocol\n"
                f"GigabitEthernet0/0/0              10.0.1.2/24           {'down' if link_down else 'up'}         {'down' if link_down else 'up'}\n"
                "GigabitEthernet0/0/1              172.16.0.1/24         up         up\n"
            )
        return (
            "*down: administratively down\n"
            "Interface                         IP Address/Mask      Physical   Protocol\n"
            "GigabitEthernet1/0/0              10.0.1.2/24           up         up\n"
        )

    def _cmd_interface_detail(self, cmd: str) -> str:
        # 提取端口名（若有）
        port = None
        for token in cmd.split():
            if token.lower().startswith("gigabitethernet") or token.lower().startswith("ethernet"):
                port = token
        # core-sw-1 GE0/0/1（故障链路交换机端）
        if port and "0/0/1" in port and self.device.name == "core-sw-1":
            if self._scenario == "flapping":
                return (
                    "GigabitEthernet0/0/1 current state : DOWN\n"
                    "Line protocol current state : DOWN\n"
                    "Description : Link to core-rtr-1 GE0/0/0\n"
                    "Switch Port, PVID : 1, TPID : 8100(Hex), The Maximum Frame Length is 9216\n"
                    "IP Sending Frames' Format is PKTFMT_ETHNT_2, Hardware address is 4c1f-cc5b-21a1\n"
                    "Port Mode: COMMON COPPER, Speed: 1000, Loopback: NONE\n"
                    "Port statistics in normal seconds: last 5 minutes\n"
                    "    Input:  5120 packets,  4123 bytes\n"
                    "    Output:  4985 packets,  3987 bytes\n"
                    "    Input bandwidth utilization  : 0.10%\n"
                    "    Output bandwidth utilization : 0.10%\n"
                    "    Input error:  1024, Output error: 0\n"
                    "    CRC:  512, Frame: 96, Runts: 41, Giants: 7\n"
                    "    Drop: 0,  Backplane drop: 0\n"
                    "Up/Down times: 42  (last flap 2026-09-04 09:12:33)\n"
                    "Last physical up time   : 2026-09-04 09:12:33\n"
                    "Last physical down time : 2026-09-04 09:11:58\n"
                )
            if self._scenario == "stp_loop":
                return (
                    "GigabitEthernet0/0/1 current state : UP\n"
                    "Line protocol current state : UP\n"
                    "Description : Link to core-rtr-1 GE0/0/0\n"
                    "Port statistics in normal seconds: last 5 minutes\n"
                    "    Input:  1823450 packets, 147289000 bytes\n"
                    "    Output: 1732210 packets, 139984000 bytes\n"
                    "    Input bandwidth utilization  : 87.3%\n"
                    "    Output bandwidth utilization : 86.1%\n"
                    "    Input error:  15238, Output error: 0\n"
                    "    Broadcast:  1387201,  Multicast: 224113\n"
                    "    Drop:  15238,  CRC: 0\n"
                    "Up/Down times: 0 (stable)\n"
                )
            return (
                "GigabitEthernet0/0/1 current state : UP\n"
                "Line protocol current state : UP\n"
                "Description : Link to core-rtr-1 GE0/0/0\n"
                "Port statistics in normal seconds: last 5 minutes\n"
                "    Input:  4230 packets,  3390 bytes\n"
                "    Output:  5120 packets,  4210 bytes\n"
                "    Input error:  0, Output error: 0\n"
                "    CRC:  0, Drop: 0\n"
                "Up/Down times: 42 days, 7 hours, 13 minutes\n"
            )
        # core-rtr-1 GE0/0/0（故障链路路由器端）
        if port and "0/0/0" in port and self.device.name == "core-rtr-1":
            if self._scenario == "flapping":
                return (
                    "GigabitEthernet0/0/0 current state : DOWN\n"
                    "Line protocol current state : DOWN\n"
                    "Description : Link to core-sw-1 GE0/0/1\n"
                    "Hardware address is 00e0-fc12-3456\n"
                    "Internet Address is 10.0.1.2/24\n"
                    "MTU 1500 bytes, BW 1000000 Kbit, DLY 10 usec\n"
                    "Input:  4910 packets,  3924 bytes\n"
                    "    Input error:  823, CRC: 401, Abort: 27, Overrun: 3\n"
                    "Output error: 0,  Collision: 0\n"
                    "Up/Down times: 40  (last flap 2026-09-04 09:12:40)\n"
                )
            return (
                "GigabitEthernet0/0/0 current state : UP\n"
                "Line protocol current state : UP\n"
                "Description : Link to core-sw-1 GE0/0/1\n"
                "Hardware address is 00e0-fc12-3456\n"
                "Internet Address is 10.0.1.2/24\n"
                "MTU 1500 bytes, BW 1000000 Kbit, DLY 10 usec\n"
                "Input error: 0, Output error: 0, CRC: 0\n"
                "Up/Down times: 42 days, 7 hours, 13 minutes\n"
            )
        return (
            "GigabitEthernet0/0/2 current state : UP\n"
            "Line protocol current state : UP\n"
            "Description : Normal uplink port\n"
            "Input:  0 error, 0 CRC   Output: 0 error\n"
            "Up/Down times: 42 days, 7 hours, 13 minutes\n"
        )

    def _cmd_ospf_peer(self) -> str:
        # flapping 场景：链路震荡导致对端邻居 Down；其他场景 OSPF 正常
        if self.device.name == "core-rtr-1":
            state = "Down" if self._scenario == "flapping" else "Full/DR"
            return (
                " OSPF Process 1 with Router ID 1.1.1.2\n"
                "Neighbors\n"
                " Area 0.0.0.0 interface 10.0.1.2(GigabitEthernet0/0/0) neighbors\n"
                " RouterID       Address         Pri DeadTime  State         Interface\n"
                f" 1.1.1.1        10.0.1.1          1    -      {state}          GigabitEthernet0/0/0\n"
            )
        if self.device.name == "core-sw-1":
            return (
                " OSPF Process 1 with Router ID 1.1.1.1\n"
                "Neighbors\n"
                " Area 0.0.0.0 interface 10.0.1.1(Vlanif1) neighbors\n"
                " RouterID       Address         Pri DeadTime  State         Interface\n"
                " 1.1.1.2        10.0.1.2          1    -      Full/DR        Vlanif1\n"
            )
        return " No neighbors"

    def _cmd_ospf_interface(self) -> str:
        return (
            " OSPF Process 1 with Router ID 1.1.1.1\n"
            " Interfaces\n"
            " Area 0.0.0.0\n"
            "  Interface           State      Address         Cost     Pri DR/BDR\n"
            "  Vlanif1             DR         10.0.1.1/24     1        1  1/2\n"
        )

    def _cmd_bgp_peer(self) -> str:
        # bgp_flap 场景：BGP 邻居 Active 抖动（物理链路正常但协议不稳）
        if self.device.name == "core-rtr-1":
            if self._scenario == "bgp_flap":
                return (
                    " BGP local router ID : 1.1.1.2\n"
                    " BGP Peer is 10.0.1.1,  remote AS 65001\n"
                    " BGP version 4,  remote router ID 1.1.1.1\n"
                    " BGP state = Active,  Up for 00:03:12\n"
                    " BGP Timer expires (on in 27 seconds)\n"
                    " Total number of sessions: 5,  Last down reason: ConnectRetry\n"
                    " Last down time: 2026-09-05 10:24:18\n"
                )
            return (
                " BGP local router ID : 1.1.1.2\n"
                " BGP Peer is 10.0.1.1,  remote AS 65001\n"
                " BGP version 4,  remote router ID 1.1.1.1\n"
                " BGP state = Established,  Up for 12 days 4 hours\n"
                " Total number of sessions: 1\n"
            )
        if self.device.name == "core-sw-1":
            if self._scenario == "bgp_flap":
                return (
                    " BGP local router ID : 1.1.1.1\n"
                    " BGP Peer is 10.0.1.2,  remote AS 65002\n"
                    " BGP version 4,  remote router ID 1.1.1.2\n"
                    " BGP state = Active,  Up for 00:03:15\n"
                    " Total number of sessions: 5,  Last down reason: ConnectRetry\n"
                )
            return (
                " BGP local router ID : 1.1.1.1\n"
                " BGP Peer is 10.0.1.2,  remote AS 65002\n"
                " BGP version 4,  remote router ID 1.1.1.2\n"
                " BGP state = Established,  Up for 12 days 4 hours\n"
            )
        return " No BGP peers configured"

    def _cmd_arp(self) -> str:
        if self._scenario == "arp_poison" and self.device.name == "core-sw-1":
            return (
                "IP Address       MAC Address    Expire(s) Type        Interface\n"
                "10.0.1.2         aabb-cc00-00ff 8          Dynamic     Vlanif1\n"
                "10.0.1.10        aabb-cc00-0001 190        Dynamic     Vlanif1\n"
                "!!! 10.0.1.2 MAC changed from 00e0-fc12-3456 to aabb-cc00-00ff\n"
            )
        if self._scenario == "arp_poison" and self.device.name == "core-rtr-1":
            return (
                "IP Address       MAC Address    Expire(s) Type        Interface\n"
                "10.0.1.1         aabb-cc00-00ff 12         Dynamic     GigabitEthernet0/0/0\n"
                "!!! 10.0.1.1 MAC changed from 4c1f-cc5b-21a1 to aabb-cc00-00ff\n"
            )
        return (
            "IP Address       MAC Address    Expire(s) Type        Interface\n"
            "10.0.1.2         00e0-fc12-3456 120        Dynamic     Vlanif1\n"
            "10.0.1.10        aabb-cc00-0001 190        Dynamic     Vlanif1\n"
        )

    def _cmd_stp(self) -> str:
        if self._scenario == "stp_loop" and self.device.name == "core-sw-1":
            return (
                "MSTID  Port                        Role  STP State     Protection\n"
                "0      GigabitEthernet0/0/1        Desi  LISTENING     None\n"
                "0      GigabitEthernet0/0/2        Desi  FORWARDING    None\n"
                "0      GigabitEthernet0/0/3        Desi  FORWARDING    None\n"
                "0      GigabitEthernet0/0/24       Root  FORWARDING    None\n"
                "Topology changes: 9526  last change: 2026-09-05 10:24:20\n"
                "!!! Frequent Topology Change Notifications (TCN) detected\n"
            )
        return (
            "MSTID  Port                        Role  STP State     Protection\n"
            "0      GigabitEthernet0/0/1        Root  FORWARDING    None\n"
            "0      GigabitEthernet0/0/2        Desi  FORWARDING    None\n"
            "0      GigabitEthernet0/0/3        Desi  FORWARDING    None\n"
            "Topology changes: 327  last change: 2026-09-04 09:12:40\n"
        )

    def _cmd_logbuffer(self) -> str:
        if self._scenario == "stp_loop" and self.device.name == "core-sw-1":
            return (
                "2026-09-05 10:24:20 core-sw-1 %%STP/4/TCN: Topology change notification received on GigabitEthernet0/0/1\n"
                "2026-09-05 10:24:18 core-sw-1 %%STP/4/TCN: Topology change notification received on GigabitEthernet0/0/2\n"
                "2026-09-05 10:24:16 core-sw-1 %%STP/4/LOOP: Loop detected on Vlanif1, port GE0/0/1 GE0/0/2 blocked\n"
                "2026-09-05 10:23:50 core-sw-1 %%STP/4/TCN: Topology change notification received on GigabitEthernet0/0/1\n"
            )
        if self._scenario == "arp_poison" and self.device.name == "core-sw-1":
            return (
                "2026-09-05 10:23:41 core-sw-1 %%ARP/5/ARP_CONFLICT: IP address 10.0.1.2 changed to MAC aabb-cc00-00ff (old 00e0-fc12-3456) on Vlanif1\n"
                "2026-09-05 10:23:12 core-sw-1 %%ARP/5/ARP_CONFLICT: IP address 10.0.1.2 changed to MAC aabb-cc00-00ff (old 00e0-fc12-3456) on Vlanif1\n"
                "2026-09-05 10:22:55 core-sw-1 %%ARP/5/ARP_DUP: Duplicate address 10.0.1.2 detected, MAC aabb-cc00-00ff\n"
            )
        if self._scenario == "bgp_flap" and self.device.name == "core-rtr-1":
            return (
                "2026-09-05 10:24:15 core-rtr-1 %%BGP/5/PEER_DOWN: BGP peer 10.0.1.1 (AS 65001) state changed from Established to Down, reason: ConnectRetry\n"
                "2026-09-05 10:21:02 core-rtr-1 %%BGP/5/PEER_UP: BGP peer 10.0.1.1 (AS 65001) state changed to Established\n"
                "2026-09-05 10:17:48 core-rtr-1 %%BGP/5/PEER_DOWN: BGP peer 10.0.1.1 (AS 65001) state changed from Established to Down\n"
            )
        if self._scenario == "acl_deny" and self.device.name == "core-sw-1":
            return (
                "2026-09-05 10:24:05 core-sw-1 %%SEC/4/ACL_DENY: Packet denied by ACL 3001 on GigabitEthernet0/0/1 inbound (src 10.0.1.1 dst 10.0.1.2 proto icmp)\n"
                "2026-09-05 10:23:55 core-sw-1 %%SEC/4/ACL_DENY: Packet denied by ACL 3001 on GigabitEthernet0/0/1 inbound (src 10.0.1.1 dst 10.0.1.2 proto icmp)\n"
            )
        return (
            "2026-09-04 09:12:33 core-sw-1 %%IFNET/4/LINK_STATE: line protocol on GigabitEthernet0/0/1 turned into DOWN state\n"
            "2026-09-04 09:12:33 core-sw-1 %%IFNET/4/LINK_STATE: line protocol on GigabitEthernet0/0/1 turned into UP state\n"
            "2026-09-04 09:11:58 core-sw-1 %%IFNET/4/LINK_STATE: line protocol on GigabitEthernet0/0/1 turned into DOWN state\n"
            "2026-09-04 09:11:58 core-sw-1 %%IFNET/4/LINK_STATE: line protocol on GigabitEthernet0/0/1 turned into UP state\n"
            "2026-09-04 09:11:31 core-sw-1 %%OSPF/5/NBR_CHG: Neighbor 10.0.1.2 changed state from FULL to DOWN\n"
        )

    def _cmd_device(self) -> str:
        return (
            "Slot  Board Type        Status       Sub Card Num\n"
            "0     S5735-L24T4X      Normal       0\n"
            "1     LPUI-24T4X        Normal       0\n"
        )

    def _cmd_current_config(self) -> str:
        if self._scenario == "acl_deny" and self.device.name == "core-sw-1":
            return (
                "interface GigabitEthernet0/0/1\n"
                " description Link to core-rtr-1\n"
                " traffic-filter inbound acl 3001\n"
                " negotiation auto\n"
                " undo shutdown\n"
                "portswitch\n"
                "#\n"
                "acl number 3001\n"
                " rule 5 deny icmp source 10.0.1.0 0.0.0.255 destination 10.0.1.2 0\n"
                "#\n"
                "interface Vlanif1\n"
                " ip address 10.0.1.1 255.255.255.0\n"
                " ospf enable 1 area 0.0.0.0\n"
                "#\n"
                "ospf 1 router-id 1.1.1.1\n"
                " area 0.0.0.0\n"
                "#\n"
            )
        return (
            "interface GigabitEthernet0/0/1\n"
            " description Link to core-rtr-1\n"
            " negotiation auto\n"
            " undo shutdown\n"
            "portswitch\n"
            "#\n"
            "interface Vlanif1\n"
            " ip address 10.0.1.1 255.255.255.0\n"
            " ospf enable 1 area 0.0.0.0\n"
            "#\n"
            "ospf 1 router-id 1.1.1.1\n"
            " area 0.0.0.0\n"
            "#\n"
        )

    def _cmd_ntp(self) -> str:
        return "clock status: synchronized\nclock source: NTP (10.0.1.254)\n"

    def _cmd_cpu_usage(self) -> str:
        if self._scenario == "stp_loop" and self.device.name == "core-sw-1":
            return (
                "CPU Usage Stat. Cycle: 60 (Second(s))\n"
                "CPU Usage            : 92%\n"
                "Max CPU Usage        : 96%  2026-09-05 10:20:00\n"
                "CPU Usage Stat. Table :\n"
                "  User   : 18%   System : 71%   Idle   : 8%\n"
                "  Interrupt: 3%\n"
            )
        return (
            "CPU Usage Stat. Cycle: 60 (Second(s))\n"
            "CPU Usage            : 5%\n"
            "Max CPU Usage        : 8%  2026-09-02 08:15:00\n"
            "CPU Usage Stat. Table :\n"
            "  User   : 2%   System : 2%   Idle   : 95%\n"
            "  Interrupt: 1%\n"
        )

    def _cmd_acl(self) -> str:
        if self._scenario == "acl_deny" and self.device.name == "core-sw-1":
            return (
                "Advanced ACL 3001, 1 rule\n"
                "Acl's step is 5\n"
                " rule 5 deny icmp source 10.0.1.0 0.0.0.255 destination 10.0.1.2 0 (12 times matched)\n"
            )
        return "Advanced ACL 3001, 0 rule\n"

    def _cmd_traffic_filter(self) -> str:
        if self._scenario == "acl_deny" and self.device.name == "core-sw-1":
            return (
                "Interface   Direction  Type      ACL/Summary\n"
                "GE0/0/1     inbound    Advanced  3001\n"
            )
        return "None\n"

    def _cmd_ping(self, cmd: str) -> str:
        # 提取目标 IP
        target = None
        for token in cmd.split():
            if token.count(".") == 3 and token.replace(".", "").isdigit():
                target = token
        if not target:
            return "Error: ping: bad address"
        # 故障链路：core-sw-1 → 10.0.1.2，丢包率随场景变化
        if target == "10.0.1.2" and self.device.name == "core-sw-1":
            if self._scenario == "acl_deny":
                return (
                    "PING 10.0.1.2: 56 data bytes, press CTRL_C to break\n"
                    "    Request time out\n"
                    "    Request time out\n"
                    "    Request time out\n"
                    "    Request time out\n"
                    "--- 10.0.1.2 ping statistics ---\n"
                    "    4 packet(s) transmitted, 0 packet(s) received, 100.0% packet loss\n"
                )
            # (丢包率, 成功包数)：flapping 4发1收=75%、stp_loop/arp_poison 4发2收=50%
            loss, got = {"flapping": (75.0, 1), "stp_loop": (50.0, 2), "arp_poison": (50.0, 2)}.get(self._scenario, (0.0, 4))
            lines = []
            for i in range(1, 5):
                if i > got:
                    lines.append("    Request time out")
                else:
                    lines.append(f"    56 bytes from 10.0.1.2: icmp_seq={i} ttl=254 time=28 ms")
            return (
                "PING 10.0.1.2: 56 data bytes, press CTRL_C to break\n"
                + "\n".join(lines)
                + "\n"
                "--- 10.0.1.2 ping statistics ---\n"
                f"    4 packet(s) transmitted, {got} packet(s) received, {loss:.1f}% packet loss\n"
                "    round-trip min/avg/max = 28/28/28 ms\n"
            )
        return (
            f"PING {target}: 56 data bytes, press CTRL_C to break\n"
            "    56 bytes from " + target + ": icmp_seq=1 ttl=254 time=1 ms\n"
            "    56 bytes from " + target + ": icmp_seq=2 ttl=254 time=1 ms\n"
            "    56 bytes from " + target + ": icmp_seq=3 ttl=254 time=1 ms\n"
            "    56 bytes from " + target + ": icmp_seq=4 ttl=254 time=1 ms\n"
            f"--- {target} ping statistics ---\n"
            "    4 packet(s) transmitted, 4 packet(s) received, 0.0% packet loss\n"
            "    round-trip min/avg/max = 1/1/1 ms\n"
        )

    def _cmd_tracert(self, cmd: str) -> str:
        target = None
        for token in cmd.split():
            if token.count(".") == 3 and token.replace(".", "").isdigit():
                target = token
        if not target:
            return "Error: tracert: bad address"
        if target == "172.16.0.1":
            return (
                "traceroute to 172.16.0.1, 30 hops max, 40 bytes packets\n"
                " 1  10.0.1.254        1 ms   1 ms   1 ms\n"
                " 2  172.16.0.1        2 ms   2 ms   1 ms\n"
            )
        if self._scenario == "acl_deny":
            return (
                f"traceroute to {target}, 30 hops max, 40 bytes packets\n"
                " 1  * * *\n"
                " 2  * * *\n"
                " 3  * * *\n"
            )
        return (
            f"traceroute to {target}, 30 hops max, 40 bytes packets\n"
            " 1  10.0.1.254        1 ms   1 ms   1 ms\n"
            " 2  * * *\n"
            " 3  * * *\n"
        )


# ---------------------------------------------------------------- Netmiko 真实连接
class NetmikoDevice:
    """通过 Netmiko（SSH）连接真实 EVE-NG 仿真设备执行命令。"""

    def __init__(self, device: Device):
        self.device = device

    async def run(self, command: str) -> str:
        try:
            from netmiko import ConnectHandler
        except ImportError as exc:  # pragma: no cover
            raise DeviceError(
                "未安装 netmiko，无法连接真实设备。请先 `pip install netmiko`，"
                "或将 DEVICE_MODE 设为 simulate。"
            ) from exc

        params = {
            "device_type": self.device.device_type,
            "host": self.device.host,
            "port": self.device.port,
            "username": self.device.username,
            "password": self.device.password,
            "timeout": 20,
            "global_delay_factor": 0.5,
        }

        def _do() -> str:
            conn = ConnectHandler(**params)
            try:
                out = conn.send_command(command, read_timeout=25)
            finally:
                conn.disconnect()
            return out

        return await asyncio.to_thread(_do)


# ---------------------------------------------------------------- 统一入口
def get_device_client(device: Device):
    """根据 device_mode 返回对应客户端。"""
    if settings.device_mode == "real":
        return NetmikoDevice(device)
    return SimulatedDevice(device)

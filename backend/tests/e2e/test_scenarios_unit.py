# -*- coding: utf-8 -*-
"""仿真故障场景库单元测试：8 个场景 × 关键命令输出自洽性断言。"""
import asyncio
import sys

sys.path.insert(0, ".")

from app.agent.devices import Device, SimulatedDevice, set_current_scenario, get_current_scenario

PASS = 0
FAIL = 0

SW1 = Device(name="core-sw-1", host="192.168.1.11", port=22, device_type="huawei",
             username="admin", password="admin123")
RTR1 = Device(name="core-rtr-1", host="192.168.1.12", port=22, device_type="huawei",
              username="admin", password="admin123")


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {extra}")


async def run(dev, cmd):
    d = SimulatedDevice(dev)
    return await d.run(cmd)


async def main():
    # ============ flapping（链路质量） ============
    print("== flapping ==")
    set_current_scenario("flapping")
    check("场景已切换", get_current_scenario() == "flapping")
    ib = await run(SW1, "display interface brief")
    check("GE0/0/1 down", "0/0/1              down" in ib, ib)
    idet = await run(SW1, "display interface GigabitEthernet0/0/1")
    check("CRC 错误增长", "CRC:  512" in idet, idet)
    op = await run(RTR1, "display ospf peer brief")
    check("OSPF 邻居 Down", "Down" in op, op)
    pg = await run(SW1, "ping 10.0.1.2")
    check("ping 75% 丢包", "75.0% packet loss" in pg, pg)
    lg = await run(SW1, "display logbuffer")
    check("日志含 LINK_STATE/OSPF 变更", "LINK_STATE" in lg and "OSPF" in lg, lg)

    # ============ stp_loop（二层环路） ============
    print("== stp_loop ==")
    set_current_scenario("stp_loop")
    ib = await run(SW1, "display interface brief")
    check("接口 up 但利用率飙升", "up       87.3%" in ib, ib)
    idet = await run(SW1, "display interface GigabitEthernet0/0/1")
    check("广播帧暴增", "Broadcast:  1387201" in idet, idet)
    stp = await run(SW1, "display stp brief")
    check("STP TCN 频繁 + 端口震荡", "Topology changes: 9526" in stp and "TCN" in stp, stp)
    cpu = await run(SW1, "display cpu-usage")
    check("CPU 92%", "92%" in cpu, cpu)
    pg = await run(SW1, "ping 10.0.1.2")
    check("ping 50% 丢包", "50.0% packet loss" in pg, pg)
    lg = await run(SW1, "display logbuffer")
    check("日志含环路告警", "LOOP" in lg and "TCN" in lg, lg)

    # ============ arp_poison（ARP 异常） ============
    print("== arp_poison ==")
    set_current_scenario("arp_poison")
    ib = await run(SW1, "display interface brief")
    check("接口物理正常(up)", "up    up" in ib and "down" not in ib, ib)
    arp = await run(SW1, "display arp")
    check("ARP 指向错误 MAC", "aabb-cc00-00ff" in arp, arp)
    lg = await run(SW1, "display logbuffer")
    check("日志含 ARP 冲突", "ARP_CONFLICT" in lg or "ARP_DUP" in lg, lg)
    pg = await run(SW1, "ping 10.0.1.2")
    check("ping 间歇不通 50%", "50.0% packet loss" in pg, pg)

    # ============ bgp_flap（BGP 抖动） ============
    print("== bgp_flap ==")
    set_current_scenario("bgp_flap")
    ib = await run(RTR1, "display interface brief")
    check("物理接口 up", "up    up" in ib and "down" not in ib, ib)
    bgp = await run(RTR1, "display bgp peer")
    check("BGP 邻居 Active", "BGP state = Active" in bgp, bgp)
    lg = await run(RTR1, "display logbuffer")
    check("日志含 BGP 邻居变更", "BGP" in lg and "PEER_DOWN" in lg, lg)
    pg = await run(SW1, "ping 10.0.1.2")
    check("ping 0% 丢包（物理通）", "0.0% packet loss" in pg, pg)

    # ============ acl_deny（ACL 拦截） ============
    print("== acl_deny ==")
    set_current_scenario("acl_deny")
    ib = await run(SW1, "display interface brief")
    check("接口 up（物理正常）", "up    up" in ib and "down" not in ib, ib)
    pg = await run(SW1, "ping 10.0.1.2")
    check("ping 100% 丢包（全超时）", "100.0% packet loss" in pg and "0 packet(s) received" in pg, pg)
    acl = await run(SW1, "display acl 3001")
    check("ACL 匹配计数增长", "12 times matched" in acl, acl)
    tf = await run(SW1, "display traffic-filter applied-record")
    check("接口应用 ACL", "GE0/0/1" in tf and "3001" in tf, tf)
    cfg = await run(SW1, "display current-configuration")
    check("配置含 traffic-filter", "traffic-filter inbound acl 3001" in cfg, cfg)
    lg = await run(SW1, "display logbuffer")
    check("日志含 ACL_DENY", "ACL_DENY" in lg, lg)

    # ============ dhcp_failure（地址池耗尽） ============
    print("== dhcp_failure ==")
    set_current_scenario("dhcp_failure")
    ib = await run(SW1, "display interface brief")
    check("接口 up（物理正常）", "up    up" in ib and "down" not in ib, ib)
    pg = await run(SW1, "ping 10.0.1.2")
    check("ping 0% 丢包（链路通）", "0.0% packet loss" in pg, pg)
    pool = await run(SW1, "display ip pool vlan1")
    check("地址池耗尽 254/254", "254" in pool and "Idle    : 0" in pool, pool)
    stat = await run(SW1, "display dhcp server statistics")
    check("DISCOVER 多 OFFER 少", "DISCOVER : 3287" in stat and "OFFER   : 12" in stat, stat)
    cfg = await run(SW1, "display current-configuration")
    check("配置含 dhcp select global", "dhcp select global" in cfg, cfg)
    lg = await run(SW1, "display logbuffer")
    check("日志含 POOL_FULL", "POOL_FULL" in lg, lg)
    tl = await run(SW1, "display fault timeline")
    check("时间线含 DHCP/POOL_FULL", "DHCP/POOL_FULL" in tl, tl)

    # ============ ospf_neighbor（MTU 不匹配卡 ExStart） ============
    print("== ospf_neighbor ==")
    set_current_scenario("ospf_neighbor")
    peer = await run(RTR1, "display ospf peer")
    check("OSPF 邻居卡 ExStart", "ExStart" in peer, peer)
    err = await run(RTR1, "display ospf error")
    check("OSPF error MTU mismatch 增长", "MTU mismatch: 128" in err, err)
    oi = await run(RTR1, "display ospf interface")
    check("OSPF 接口标注 MTU 不一致", "MTU 1500" in oi and "1492" in oi, oi)
    pg = await run(RTR1, "ping 10.0.1.1")
    check("ping 0% 丢包（三层通）", "0.0% packet loss" in pg, pg)
    cfg = await run(RTR1, "display current-configuration")
    check("配置含 mtu 1500", "mtu 1500" in cfg, cfg)
    lg = await run(RTR1, "display logbuffer")
    check("日志含 OSPF/MTU", "OSPF/5/MTU" in lg, lg)
    tl = await run(RTR1, "display fault timeline")
    check("时间线含 OSPF/MTU", "OSPF/MTU" in tl, tl)

    # ============ link_congestion（上联拥塞） ============
    print("== link_congestion ==")
    set_current_scenario("link_congestion")
    ib = await run(SW1, "display interface brief")
    check("GE0/0/1 利用率打满", "96.2%" in ib and "97.8%" in ib, ib)
    det = await run(SW1, "display interface GigabitEthernet0/0/1")
    check("输出队列丢弃增长", "Output queue drop: 118234" in det, det)
    qos = await run(SW1, "display qos queue statistics")
    check("QoS 队列丢弃", "Total drop" in qos and "118,234" in qos, qos)
    pg = await run(SW1, "ping 10.0.1.2")
    check("ping 25% 丢包+高时延", "25.0% packet loss" in pg and "112 ms" in pg, pg)
    cpu = await run(SW1, "display cpu-usage")
    check("CPU 正常（区别于环路）", "CPU Usage            : 5%" in cpu, cpu)
    lg = await run(SW1, "display logbuffer")
    check("日志含 QOS/DROP", "QOS/4/DROP" in lg, lg)
    tl = await run(SW1, "display fault timeline")
    check("时间线含 QOS/DROP", "QOS/DROP" in tl, tl)

    # ============ 恢复默认 ============
    set_current_scenario("flapping")
    check("恢复默认 flapping", get_current_scenario() == "flapping")

    print(f"\n结果：{PASS} 通过，{FAIL} 失败")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())

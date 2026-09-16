# -*- coding: utf-8 -*-
"""方案 A · 仿真 SSH 服务端 × Netmiko 真实链路测试。

在测试内启动 sim_ssh 服务端（独立端口 + 临时 host key），用 Netmiko 以
huawei device_type 走真实 SSH/TCP 协议栈连接，断言：
  - SSH 握手/密码认证/PTY/shell 交互
  - 命令回显 + 分页抑制（screen-length）
  - 场景剧本输出正确、切换场景后输出联动
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, ".")

from app.agent.devices import Device, set_current_scenario, get_current_scenario
from app.sim_ssh import _load_or_create_host_key, _spawn_device_server

PASS = 0
FAIL = 0
STOP = threading.Event()

TEST_PORT = 22290
TEST_HOST_KEY = Path(__file__).resolve().parents[1] / "data" / "test_sim_ssh_host_rsa"

DEV = Device(name="core-sw-1", host="127.0.0.1", port=TEST_PORT, device_type="huawei",
             username="admin", password="admin123")


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {extra}")


def main():
    host_key = _load_or_create_host_key(TEST_HOST_KEY)
    _spawn_device_server(DEV, TEST_PORT, host_key, STOP)
    time.sleep(1.0)

    from netmiko import ConnectHandler

    # 1) 认证 + 提示符
    c = ConnectHandler(device_type="huawei", host="127.0.0.1", port=TEST_PORT,
                       username="admin", password="admin123")
    check("SSH 认证成功，提示符正确", c.base_prompt == "core-sw-1", repr(c.base_prompt))

    # 2) 场景剧本：flapping
    set_current_scenario("flapping")
    ib = c.send_command("display interface brief")
    check("flapping: GE0/0/1 down", "GigabitEthernet0/0/1              down" in ib, ib[:120])
    pg = c.send_command("ping 10.0.1.2")
    check("flapping: ping 75% 丢包", "75.0% packet loss" in pg, pg[:120])

    # 3) 场景切换联动：stp_loop
    set_current_scenario("stp_loop")
    ib2 = c.send_command("display interface brief")
    check("stp_loop: 接口 up 且利用率高", "87.3%" in ib2 and "GigabitEthernet0/0/1              up" in ib2, ib2[:120])
    cpu = c.send_command("display cpu-usage")
    check("stp_loop: CPU 92%", "CPU Usage            : 92%" in cpu, cpu[:120])

    # 4) 分页抑制命令不中断会话（后续命令仍可用）
    _ = c.send_command("screen-length 0 temporary")
    ver = c.send_command("display version")
    check("分页抑制后会话正常", "VRP" in ver, ver[:80])

    # 5) 时间线命令
    set_current_scenario("stp_loop")
    tl = c.send_command("display fault timeline")
    check("时间线输出（STP/TCN）", "STP/TCN" in tl and "scenario=stp_loop" in tl, tl[:120])

    c.disconnect()
    check("Netmiko 断开正常", True)

    # 恢复场景
    set_current_scenario("flapping")
    check("恢复默认 flapping", get_current_scenario() == "flapping")

    print(f"\n结果：{PASS} 通过，{FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    try:
        main()
    finally:
        STOP.set()

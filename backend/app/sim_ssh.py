# -*- coding: utf-8 -*-
"""仿真 SSH 服务端（优化方案 A：Netmiko 真实链路第一步）。

用 paramiko 实现一个轻量 SSH 服务端：每台仿真设备监听一个独立端口，
Netmiko 以 huawei device_type 走「真实 TCP/SSH 握手 → 密码认证 → 命令交互」，
命令响应复用 backend/app/agent/devices.py 的 SimulatedDevice 仿真剧本。

由此在**不依赖 EVE-NG / 真实硬件**的前提下，验证整条真实协议栈链路：
Netmiko 驱动层（huawei 适配）→ SSH 传输层 → 设备输出解析（提示符/分页抑制）。
与主服务共享同一份场景状态（set_current_scenario 切换后，SSH 侧输出同步变化）。

用法：
    python -m app.sim_ssh                  # 按 devices.json 全部设备，端口从 2222 起
    python -m app.sim_ssh --port 2222      # 仅第一台设备（core-sw-1）监听 2222
    python -m app.sim_ssh --port 2222 --device core-rtr-1   # 指定设备
环境变量：
    SIM_SSH_BASE_PORT  默认 2222，设备按 devices.json 顺序递增
    SIM_SSH_HOST_KEY   host key 路径，默认 backend/data/sim_ssh_host_rsa
"""
import argparse
import asyncio
import socket
import socketserver
import sys
import threading
from pathlib import Path

import paramiko

from app.agent.devices import SimulatedDevice, find_device, get_devices
from app.config import DEVICES_FILE

HOST_KEY_PATH = Path(__file__).resolve().parents[1] / "data" / "sim_ssh_host_rsa"


def _load_or_create_host_key(path: Path) -> paramiko.RSAKey:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return paramiko.RSAKey(filename=str(path))
    key = paramiko.RSAKey.generate(2048)
    key.write_private_key_file(str(path))
    print(f"[sim-ssh] 已生成 host key: {path}")
    return key


class SimSSHServer(paramiko.ServerInterface):
    """SSH 服务端接口：密码认证 + 交互会话。"""

    def __init__(self, device, allowed_user: str, allowed_password: str):
        self.device = device
        self._user = allowed_user
        self._pass = allowed_password
        self._sim = SimulatedDevice(device)
        self.event = threading.Event()

    def check_auth_password(self, username, password):
        if username == self._user and password == self._pass:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_auth_none(self, username):
        return paramiko.AUTH_FAILED

    def check_channel_request(self, kind, chanid):
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_shell_request(self, channel):
        self.event.set()
        return True

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        # Netmiko 连接时会请求 PTY（vt100），必须接受
        return True

    def check_channel_window_change_request(self, channel, width, height, pixelwidth, pixelheight):
        return True

    def check_channel_exec_request(self, channel, command):
        self.event.set()
        return True

    def get_allowed_auths(self, username):
        return "password"

    # -- 交互实现 --
    def _prompt(self) -> bytes:
        # 华为提示符：<hostname>
        return f"<{self.device.name}>".encode("utf-8")

    def _respond(self, channel, line: str):
        """处理一行命令：回显 + 输出 + 提示符（真实设备行为：输入命令必有回显）。"""
        cmd = line.strip()
        if not cmd:
            channel.send(b"\r\n" + self._prompt())
            return True
        # 会话退出命令
        if cmd.lower() in {"quit", "exit", "return", "q"}:
            channel.send(b"\r\n")
            return False
        # Netmiko 分页抑制 / 终端控制命令：回显命令本身（Netmiko 以回显作为完成标志），无输出
        if cmd.lower() in {
            "screen-length 0 temporary",
            "terminal monitor",
            "undo terminal monitor",
            "terminal length 0",
            "terminal width 200",
            "undo smart",
        }:
            channel.send(f"{cmd}\r\n".encode("utf-8") + self._prompt())
            return True
        # 设备命令：回显命令本身，再返回输出
        try:
            out = asyncio.run(self._sim.run(cmd))
        except Exception as exc:  # 仿真异常不中断会话
            out = f"Error: {exc}"
        payload = "\r\n".join([cmd] + out.splitlines())
        channel.send(payload.encode("utf-8", errors="replace") + b"\r\n" + self._prompt())
        return True

    def serve_channel(self, channel: paramiko.Channel):
        try:
            channel.settimeout(600)  # 10 分钟无输入自动断开
            channel.send(self._prompt())
            buf = b""
            while True:
                try:
                    chunk = channel.recv(4096)
                except socket.timeout:
                    break
                if not chunk:
                    break
                buf += chunk
                # 按行处理（兼容 \n 与 \r\n）
                while b"\n" in buf:
                    raw, _, rest = buf.partition(b"\n")
                    buf = rest
                    line = raw.decode("utf-8", errors="replace").rstrip("\r")
                    if not self._respond(channel, line):
                        return
                if len(buf) > 65536:  # 防恶意超大缓冲
                    buf = b""
        except Exception:
            pass
        finally:
            try:
                channel.close()
            except Exception:
                pass


def _spawn_device_server(device, port: int, host_key: paramiko.RSAKey, stop_event: threading.Event):
    """为单台设备启动一个监听线程。"""

    def _handle(client_sock):
        transport = None
        try:
            transport = paramiko.Transport(client_sock)
            transport.add_server_key(host_key)
            server = SimSSHServer(device, device.username, device.password)
            try:
                transport.start_server(server=server)
            except paramiko.SSHException:
                return
            # 等待认证完成
            while not server.event.is_set():
                if not transport.is_active():
                    return
                server.event.wait(0.2)
            channel = transport.accept(5)
            if channel is not None:
                server.serve_channel(channel)
        except Exception:
            pass
        finally:
            if transport:
                try:
                    transport.close()
                except Exception:
                    pass

    def _accept_loop():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", port))
            srv.listen(16)
            srv.settimeout(1.0)
            print(f"[sim-ssh] {device.name} -> 127.0.0.1:{port}（账号 {device.username} / {device.password}，场景随主服务切换）")
            while not stop_event.is_set():
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                threading.Thread(target=_handle, args=(conn,), daemon=True).start()

    t = threading.Thread(target=_accept_loop, daemon=True)
    t.start()
    return t


def main():
    parser = argparse.ArgumentParser(description="NetOps 仿真 SSH 服务端（方案 A）")
    parser.add_argument("--port", type=int, default=None, help="监听端口（默认 base_port=2222 + 设备序号）")
    parser.add_argument("--device", default=None, help="仅监听指定设备（默认全部）")
    parser.add_argument("--host-key", default=str(HOST_KEY_PATH), help="host key 路径")
    args = parser.parse_args()

    devices = get_devices()
    if not devices:
        print(f"[sim-ssh] 未找到设备清单：{DEVICES_FILE}", file=sys.stderr)
        sys.exit(1)

    target = [d for d in devices if args.device is None or d.name == args.device]
    if not target:
        print(f"[sim-ssh] 未找到设备 {args.device}，可用：{', '.join(d.name for d in devices)}", file=sys.stderr)
        sys.exit(1)

    host_key = _load_or_create_host_key(Path(args.host_key))
    stop_event = threading.Event()
    threads = []
    for i, dev in enumerate(target):
        port = args.port if (args.port is not None and len(target) == 1) else 2222 + i
        threads.append(_spawn_device_server(dev, port, host_key, stop_event))

    print("[sim-ssh] 服务端已启动（Ctrl+C 退出）。可用 Netmiko 连接：")
    print(
        "    from netmiko import ConnectHandler\n"
        "    c = ConnectHandler(device_type='huawei', host='127.0.0.1', port=2222,\n"
        "                       username='admin', password='admin123')\n"
        "    print(c.send_command('display interface brief'))"
    )
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n[sim-ssh] 停止。")
        stop_event.set()


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
NetOps AI Assistant · 一键启动器

双击此 exe（或运行 launcher.py）：
  1. 检查 Docker 引擎是否可用
  2. 检查 3 个 FRR 容器（frr1/2/3）是否在运行；未运行则 docker compose 拉起并等待就绪
  3. 检查后端服务（127.0.0.1:8000）是否在运行；未运行则以 DEVICE_MODE=real 启动 uvicorn
  4. 全部就绪后自动打开浏览器页面

日志写入 tools/launcher.log；后端日志写入 tools/uvicorn_out.log / uvicorn_err.log。
"""
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

# ----------------------------------------------------------------------------
# 路径定位：exe 打包后 = exe 所在目录；脚本运行 = 脚本所在目录
# ----------------------------------------------------------------------------
BASE = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
BACKEND = BASE / "backend"
VENV_PY = BACKEND.parent / ".venv" / "Scripts" / "python.exe"
COMPOSE = None
for cand in (BASE / "docker-compose.frr.yml", BACKEND / "docker-compose.frr.yml"):
    if cand.exists():
        COMPOSE = cand
        break
LOG_FILE = BASE / "tools" / "launcher.log"
FRR_NAMES = ("frr1", "frr2", "frr3")
HEALTH_URL = "http://127.0.0.1:8000/api/health"

# Docker Desktop 常见安装路径（非 PATH 时的兜底探测）
DOCKER_CANDIDATES = [
    "docker",
    r"C:\Users\Curry\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe",
    r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
]


def log(msg: str):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def run(cmd: list[str], timeout: int = 120, cwd=None) -> tuple[int, str]:
    """运行命令，返回 (exit_code, output)。错误输出合并到 output。"""
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return -1, f"命令不存在: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -2, f"命令超时: {' '.join(cmd)}"


def find_docker() -> str | None:
    for c in DOCKER_CANDIDATES:
        if c == "docker":
            if shutil_which("docker"):
                return "docker"
            continue
        if Path(c).exists():
            return c
    return None


def shutil_which(name: str) -> str | None:
    import shutil

    return shutil.which(name)


def docker_ok(docker: str) -> bool:
    code, out = run([docker, "info", "--format", "{{.ServerVersion}}"], timeout=30)
    return code == 0


def containers_running(docker: str) -> list[str]:
    code, out = run([docker, "ps", "--format", "{{.Names}}"], timeout=30)
    if code != 0:
        return []
    running = set(out.splitlines())
    return [n for n in FRR_NAMES if n in running]


def start_containers(docker: str) -> bool:
    """拉起容器并等待 SSH/FRR 就绪。返回是否成功。"""
    if not COMPOSE:
        log("[失败] 找不到 docker-compose.frr.yml，无法拉起容器")
        return False
    log(f"拉起容器: docker compose -f {COMPOSE.name} up -d ...")
    code, out = run([docker, "compose", "-f", str(COMPOSE), "up", "-d"], timeout=180)
    if code != 0:
        log(f"[失败] compose up 失败:\n{out[-800:]}")
        return False
    # 等待容器全部就绪（最多 90s）：docker exec vtysh 能返回 = 协议进程就绪
    deadline = time.time() + 90
    while time.time() < deadline:
        running = containers_running(docker)
        if len(running) == 3:
            ready = all(
                run([docker, "exec", n, "vtysh", "-c", "show version"], timeout=20)[0] == 0
                for n in FRR_NAMES
            )
            if ready:
                log("3 个 FRR 容器已就绪（OSPF/eBGP 协议进程可访问）")
                return True
        time.sleep(5)
    log("[失败] 等待容器就绪超时（90s），请打开 Docker Desktop 检查容器状态")
    return False


def backend_ok() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def start_backend() -> bool:
    """以 DEVICE_MODE=real 启动 uvicorn（独立进程，日志落盘）。"""
    if not VENV_PY.exists():
        log(f"[失败] 找不到虚拟环境 Python: {VENV_PY}（请先 python -m venv .venv 并安装依赖）")
        return False
    log("启动后端服务（DEVICE_MODE=real, 127.0.0.1:8000）...")
    tools_dir = BASE / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["DEVICE_MODE"] = "real"
    env["PYTHONUTF8"] = "1"
    with open(tools_dir / "uvicorn_out.log", "w", encoding="utf-8") as fo, open(
        tools_dir / "uvicorn_err.log", "w", encoding="utf-8"
    ) as fe:
        subprocess.Popen(
            [str(VENV_PY), "-X", "utf8", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=str(BACKEND),
            env=env,
            stdout=fo,
            stderr=fe,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )
    deadline = time.time() + 60
    while time.time() < deadline:
        if backend_ok():
            log("后端服务已就绪（/api/health OK）")
            return True
        time.sleep(3)
    log("[失败] 后端服务 60s 内未就绪，详见 tools/uvicorn_err.log")
    return False


def main():
    # 控制台编码兜底：避免 GBK 终端打印特殊字符崩溃
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("=" * 60, flush=True)
    print("  NetOps AI Assistant · 一键启动器", flush=True)
    print(f"  项目目录: {BASE}", flush=True)
    print("=" * 60, flush=True)
    log("==== 启动器运行 ====")

    # 1. Docker
    docker = find_docker()
    if not docker:
        log("[失败] 未找到 Docker 客户端。请先安装并启动 Docker Desktop")
        input("按回车退出...")
        return
    log(f"找到 Docker: {docker}")
    if not docker_ok(docker):
        log("[提示] Docker 引擎未就绪，正在等待 Docker Desktop 启动（最多 60s）...")
        deadline = time.time() + 60
        ok = False
        while time.time() < deadline:
            if docker_ok(docker):
                ok = True
                break
            time.sleep(5)
        if not ok:
            log("[失败] Docker 引擎不可用。请手动打开 Docker Desktop，等待左下角变绿后重试")
            input("按回车退出...")
            return
    log(f"Docker 引擎可用（Server {run([docker, 'info', '--format', '{{.ServerVersion}}'])[1].strip()}）")

    # 2. 容器
    running = containers_running(docker)
    if len(running) == 3:
        log(f"容器已在运行: {', '.join(sorted(running))}（跳过启动）")
    else:
        log(f"容器缺省: 运行中 {len(running)}/3 , 尝试拉起")
        if not start_containers(docker):
            input("按回车退出...")
            return

    # 3. 后端
    if backend_ok():
        log("后端服务已在运行（跳过启动）")
    else:
        if not start_backend():
            input("按回车退出...")
            return

    # 4. 用 pywebview 打开独立原生窗口（不再依赖系统浏览器）
    url = "http://127.0.0.1:8000/"
    log(f"全部就绪，打开桌面窗口: {url}")
    try:
        import webview
        icon_path = str(BASE / "frontend" / "assets" / "nahida.ico")
        if not Path(icon_path).exists():
            icon_path = None
        webview.create_window(
            title="NetOps AI Assistant · 运维管家",
            url=url,
            width=1440,
            height=900,
            min_size=(1024, 680),
            resizable=True,
        )
        print("-" * 60, flush=True)
        print("  启动完成 [OK]，桌面窗口已打开", flush=True)
        print("  关闭窗口即退出；后端服务在后台运行", flush=True)
        print("  日志位置: tools/launcher.log", flush=True)
        print("-" * 60, flush=True)
        webview.start()
    except Exception as exc:
        log(f"[提示] pywebview 启动失败（{exc}），回退到系统浏览器")
        webbrowser.open(url)


if __name__ == "__main__":
    main()


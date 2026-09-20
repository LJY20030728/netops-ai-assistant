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
# windowed 打包模式兜底：console=False 时 sys.stdin/stdout/stderr 均为 None，
# 任何 print / logging / input / uvicorn 访问 .isatty() 都会崩，这里先重定向
# ----------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    # windowed 模式：stdin 无效置空；stdout/stderr 落到日志文件以便排查问题
    tools_dir = Path(sys.executable).resolve().parent / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")
    log_fp = tools_dir / "uvicorn_err.log"
    log_fo = tools_dir / "uvicorn_out.log"
    if sys.stdout is None:
        sys.stdout = open(log_fo, "a", encoding="utf-8", errors="replace")
    if sys.stderr is None:
        sys.stderr = open(log_fp, "a", encoding="utf-8", errors="replace")


def safe_pause(seconds: float = 3.0):
    """windowed 模式无控制台，input() 会因 stdin=None 崩溃；用短暂等待代替。"""
    if not getattr(sys, "frozen", False):
        try:
            input("按回车退出...")
            return
        except Exception:
            pass
    time.sleep(seconds)

# ----------------------------------------------------------------------------
# 路径定位：exe 打包后 = exe 所在目录；脚本运行 = 脚本所在目录
# ----------------------------------------------------------------------------
BASE = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
BACKEND = BASE / "backend"
VENV_PY = BACKEND.parent / ".venv" / "Scripts" / "python.exe"
COMPOSE = None
for cand in (
    BASE / "docker-compose.frr.yml",
    BASE / "_internal" / "docker-compose.frr.yml",
    BACKEND / "docker-compose.frr.yml",
):
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
# Docker Desktop 主程序（engine 未就绪时自动拉起）
DOCKER_DESKTOP_CANDIDATES = [
    r"C:\Users\Curry\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe",
    r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
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
            stdin=subprocess.DEVNULL,  # 关键：windowed 模式下父进程 stdin 句柄无效，子进程继承会 0xc0000142
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


def try_launch_docker_desktop() -> bool:
    """Docker engine 未就绪时尝试拉起 Docker Desktop，返回是否找到主程序。"""
    for c in DOCKER_DESKTOP_CANDIDATES:
        if Path(c).exists():
            try:
                subprocess.Popen(
                    [c],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                continue
    return False


def containers_running(docker: str) -> list[str]:
    code, out = run([docker, "ps", "--format", "{{.Names}}"], timeout=30)
    if code != 0:
        return []
    running = set(out.splitlines())
    return [n for n in FRR_NAMES if n in running]


def _wait_frr_ready(docker: str, timeout: int = 90) -> bool:
    """等待 3 个容器全部就绪（docker exec vtysh 能返回）。"""
    deadline = time.time() + timeout
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
    log("[失败] 容器就绪超时")
    return False


def start_containers(docker: str) -> bool:
    """拉起容器并等待 SSH/FRR 就绪。优先 docker start（容器已存在），回退 compose up。"""
    # Docker Desktop 重启后容器为 stopped：直接 start 最快，不依赖 compose 文件
    code, out = run([docker, "ps", "-a", "--format", "{{.Names}}"], timeout=30)
    if code == 0:
        have = set(out.splitlines())
        to_start = [n for n in FRR_NAMES if n in have]
        if to_start:
            log(f"容器已存在（stopped），docker start: {', '.join(to_start)} ...")
            scode, sout = run([docker, "start", *to_start], timeout=120)
            if scode == 0:
                return _wait_frr_ready(docker)
            log(f"[提示] docker start 失败，回退 compose up:\n{sout[-300:]}")
    if not COMPOSE:
        log("[失败] 找不到 docker-compose.frr.yml，无法拉起容器")
        return False
    log(f"拉起容器: docker compose -f {COMPOSE.name} up -d ...")
    code, out = run([docker, "compose", "-f", str(COMPOSE), "up", "-d"], timeout=180)
    if code != 0:
        log(f"[失败] compose up 失败:\n{out[-800:]}")
        return False
    return _wait_frr_ready(docker)


def backend_ok() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def start_backend() -> bool:
    """启动 uvicorn：打包模式内嵌线程起；开发模式子进程起。"""
    tools_dir = BASE / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)

    if getattr(sys, "frozen", False):
        # 打包模式：在当前进程的子线程里起 uvicorn
        log("打包模式：内嵌 uvicorn 启动后端...")
        os.environ["DEVICE_MODE"] = "real"
        os.environ["PYTHONUTF8"] = "1"
        # 指向用户的 HuggingFace 模型缓存（bge embedding）
        os.environ.setdefault("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        # 打包后 backend 代码在 _internal/backend 下
        backend_dir = BASE / "_internal" / "backend"
        if not backend_dir.exists():
            backend_dir = BASE / "backend"
        os.chdir(backend_dir)
        sys.path.insert(0, str(backend_dir))
        import uvicorn
        # log_config=None 跳过 uvicorn 默认 dictConfig，避免实例化 DefaultFormatter
        # （其 __init__ 会访问 sys.stdout.isatty()，windowed 模式下直接崩溃）
        config = uvicorn.Config("app.main:app", host="127.0.0.1", port=8000, log_level="warning", log_config=None)
        server = uvicorn.Server(config)
        import threading
        t = threading.Thread(target=server.run, daemon=True)
        t.start()
    else:
        if not VENV_PY.exists():
            log(f"[失败] 找不到虚拟环境 Python: {VENV_PY}（请先 python -m venv .venv 并安装依赖）")
            return False
        log("启动后端服务（DEVICE_MODE=real, 127.0.0.1:8000）...")
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

    deadline = time.time() + 90
    while time.time() < deadline:
        if backend_ok():
            log("后端服务已就绪（/api/health OK）")
            return True
        time.sleep(3)
    log("[失败] 后端服务 90s 内未就绪")
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
        log("[失败] 未找到 Docker 客户端。请先安装 Docker Desktop")
        safe_pause()
        return
    log(f"找到 Docker: {docker}")
    if not docker_ok(docker):
        log("[提示] Docker 引擎未就绪，尝试启动 Docker Desktop...")
        if try_launch_docker_desktop():
            log("已拉起 Docker Desktop，等待引擎就绪（最多 120s）...")
            deadline = time.time() + 120
            while time.time() < deadline:
                if docker_ok(docker):
                    break
                time.sleep(5)
        if not docker_ok(docker):
            log("[失败] Docker 引擎不可用。请手动打开 Docker Desktop，等待左下角变绿后重试")
            safe_pause()
            return
    log(f"Docker 引擎可用（Server {run([docker, 'info', '--format', '{{.ServerVersion}}'])[1].strip()}）")

    # 2. 容器
    running = containers_running(docker)
    if len(running) == 3:
        log(f"容器已在运行: {', '.join(sorted(running))}（跳过启动）")
    else:
        log(f"容器缺省: 运行中 {len(running)}/3 , 尝试拉起")
        if not start_containers(docker):
            safe_pause()
            return

    # 3. 后端
    if backend_ok():
        log("后端服务已在运行（跳过启动）")
    else:
        if not start_backend():
            safe_pause()
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


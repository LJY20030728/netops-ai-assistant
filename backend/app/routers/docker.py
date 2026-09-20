"""Docker 控制路由：状态检测与应用内启动。"""
import asyncio
import os
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, Depends

from app.agent.frr_lab import _DOCKER_CANDIDATES
from app.security.auth import require_role

router = APIRouter(prefix="/api/docker", tags=["docker"])

# windowed 打包环境下禁止子进程弹出黑色控制台窗口
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _docker_running(docker: str) -> str | None:
    """同步探测 docker 引擎是否就绪，返回版本号或 None。"""
    proc = subprocess.run([docker, "version", "--format", "{{.Server.Version}}"],
                          capture_output=True, text=True, timeout=3, encoding="utf-8", errors="replace",
                          creationflags=_NO_WINDOW)
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return None


def _wait_docker_and_up(docker: str, dd_exe: str, compose_cwd: str) -> dict:
    """同步等待 Docker Desktop 就绪并拉起容器（最多 60s）。整体放线程池，不阻塞事件循环。"""
    try:
        subprocess.Popen([dd_exe], shell=False, creationflags=_NO_WINDOW)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"启动 Docker Desktop 失败：{exc}"}
    for _ in range(20):
        time.sleep(3)
        version = _docker_running(docker)
        if version:
            proc = subprocess.run([docker, "compose", "-f", "docker-compose.frr.yml", "up", "-d"],
                                  cwd=compose_cwd, capture_output=True, text=True, timeout=60,
                                  encoding="utf-8", errors="replace", creationflags=_NO_WINDOW)
            if proc.returncode == 0:
                return {"ok": True, "message": f"Docker {version} 已启动，容器已拉起"}
            return {"ok": False, "message": f"Docker 已就绪但容器拉起失败：{proc.stderr[:200]}"}
    return {"ok": False, "message": "Docker 引擎 60 秒内未就绪，请手动检查 Docker Desktop 是否运行"}


@router.get("/status")
async def docker_status(role: str = Depends(require_role("viewer"))):
    from app.agent.frr_lab import _find_docker
    try:
        docker = _find_docker()
        version = _docker_running(docker)
        if not version:
            return {"ok": True, "available": False, "message": "Docker 引擎未运行"}
        running = subprocess.run([docker, "ps", "--format", "{{.Names}}"],
                                 capture_output=True, text=True, timeout=5, encoding="utf-8", errors="replace",
                                 creationflags=_NO_WINDOW)
        containers = [ln.strip() for ln in running.stdout.splitlines() if ln.strip()]
        return {"ok": True, "available": True, "version": version, "containers": containers}
    except Exception as exc:  # noqa: BLE001
        return {"ok": True, "available": False, "message": str(exc)}


@router.post("/start")
async def docker_start(role: str = Depends(require_role("operator"))):
    dd_exe = None
    for cand in [r"C:\Users\Curry\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe",
                 r"C:\Program Files\Docker\Docker\Docker Desktop.exe"]:
        if os.path.exists(cand):
            dd_exe = cand
            break
    if not dd_exe:
        return {"ok": False, "message": "未找到 Docker Desktop，请先安装 Docker Desktop"}

    docker = next((c for c in _DOCKER_CANDIDATES if os.path.exists(c)), None)
    if not docker:
        return {"ok": False, "message": "未找到 docker CLI"}

    compose_cwd = str(Path(__file__).resolve().parents[3].parent)
    # 同步轮询移入线程池：不阻塞 FastAPI 事件循环
    return await asyncio.to_thread(_wait_docker_and_up, docker, dd_exe, compose_cwd)

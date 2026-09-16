"""Docker 控制路由：状态检测与应用内启动。"""
import os
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, Depends

from app.agent.frr_lab import _DOCKER_CANDIDATES
from app.security.auth import require_role

router = APIRouter(prefix="/api/docker", tags=["docker"])


@router.get("/status")
async def docker_status(role: str = Depends(require_role("viewer"))):
    from app.agent.frr_lab import _find_docker
    try:
        docker = _find_docker()
        proc = subprocess.run([docker, "version", "--format", "{{.Server.Version}}"],
                              capture_output=True, text=True, timeout=5, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            return {"ok": True, "available": False, "message": "Docker 引擎未运行"}
        running = subprocess.run([docker, "ps", "--format", "{{.Names}}"],
                                 capture_output=True, text=True, timeout=5, encoding="utf-8", errors="replace")
        containers = [ln.strip() for ln in running.stdout.splitlines() if ln.strip()]
        return {"ok": True, "available": True, "version": proc.stdout.strip(), "containers": containers}
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
    try:
        subprocess.Popen([dd_exe], shell=False)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"启动 Docker Desktop 失败：{exc}"}

    docker = next((c for c in _DOCKER_CANDIDATES if os.path.exists(c)), None)
    if not docker:
        return {"ok": False, "message": "未找到 docker CLI"}

    compose_cwd = str(Path(__file__).resolve().parents[3].parent)
    for _ in range(20):
        time.sleep(3)
        try:
            proc = subprocess.run([docker, "version", "--format", "{{.Server.Version}}"],
                                  capture_output=True, text=True, timeout=3, encoding="utf-8", errors="replace")
            if proc.returncode == 0 and proc.stdout.strip():
                subprocess.run([docker, "compose", "-f", "docker-compose.frr.yml", "up", "-d"],
                               cwd=compose_cwd, capture_output=True, text=True, timeout=60,
                               encoding="utf-8", errors="replace")
                return {"ok": True, "message": f"Docker {proc.stdout.strip()} 已启动，容器已拉起"}
        except Exception:  # noqa: BLE001
            pass
    return {"ok": False, "message": "Docker 引擎 60 秒内未就绪，请手动检查 Docker Desktop 是否运行"}

"""拓扑与 FRR 设备路由。"""
import json
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends

from app.config import settings
from app.agent import fault_state
from app.agent.devices import get_devices
from app.security import audit
from app.security.auth import require_role

router = APIRouter(prefix="/api", tags=["topology"])


@router.get("/devices")
async def devices_list(role: str = Depends(require_role("viewer"))):
    from app.agent.devices import get_current_scenario
    return {
        "mode": settings.device_mode,
        "scenario": get_current_scenario() if settings.device_mode == "simulate" else None,
        "devices": [
            {"name": d.name, "host": d.host, "role": d.role, "device_type": d.device_type}
            for d in get_devices()
        ],
    }


@router.get("/topology/real")
async def topology_real(role: str = Depends(require_role("viewer"))):
    from app.agent.frr_lab import FrrLab, _find_docker
    if settings.device_mode != "real":
        return {"ok": False, "mode": settings.device_mode,
                "message": "当前为 simulate 模式，真实拓扑仅在 DEVICE_MODE=real 下可用"}
    try:
        docker = _find_docker()
        proc = subprocess.run([docker, "ps", "--format", "{{.Names}}"],
                              capture_output=True, text=True, timeout=5, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            return {"ok": False, "mode": "real", "docker_available": False,
                    "message": f"Docker 不可用：{proc.stderr[:200]}"}
        running = {ln.strip() for ln in proc.stdout.splitlines() if ln.strip()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "mode": "real", "docker_available": False, "message": f"Docker 引擎未连接：{exc}"}

    all_devs = {d.name: d for d in get_devices() if d.device_type == "frr"}
    live_devs = {n: d for n, d in all_devs.items() if n in running}
    faults = fault_state.snapshot()
    results = {}
    for name, d in sorted(live_devs.items()):
        entry = await FrrLab(d).status_all()
        entry["active_faults"] = faults.get(name, {})
        results[name] = entry
    return {"ok": True, "mode": "real", "docker_available": True,
            "containers_running": sorted(running), "devices": results, "faults": faults}


@router.post("/frr/recover-all")
async def frr_recover_all(role: str = Depends(require_role("admin"))):
    from app.agent.frr_lab import FrrLab, _LEGAL
    if settings.device_mode != "real":
        return {"ok": False, "message": "真实 FRR 实验室仅在 DEVICE_MODE=real 下可用"}
    devs = {d.name: d for d in get_devices() if d.device_type == "frr"}
    recovered, errors = [], []
    for name, d in sorted(devs.items()):
        lab = FrrLab(d)
        for fault, iface in _LEGAL.get(name, {}).items():
            try:
                await lab.recover(fault, iface)
                recovered.append(f"{name}/{fault}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name}/{fault}: {exc}")
    audit.log("frr", actor=role, action="recover_all",
              detail=json.dumps({"recovered": recovered, "errors": errors}, ensure_ascii=False))
    fault_state.clear_all()
    return {"ok": True, "recovered": recovered, "errors": errors}


@router.get("/fault/state")
async def fault_state_get(role: str = Depends(require_role("viewer"))):
    return {"ok": True, "faults": fault_state.snapshot()}

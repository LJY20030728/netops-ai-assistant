"""仿真故障场景切换路由（simulate 模式）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import settings
from app.agent.devices import get_current_scenario, set_current_scenario
from app.security import audit
from app.security.auth import require_role

router = APIRouter(prefix="/api/sim", tags=["sim"])

AVAILABLE = ["flapping", "stp_loop", "arp_poison", "bgp_flap", "acl_deny"]


class ScenarioBody(BaseModel):
    scenario: str = Field(..., min_length=1, max_length=32)


@router.get("/scenario")
async def sim_scenario_get():
    return {"mode": settings.device_mode, "scenario": get_current_scenario(), "available": AVAILABLE}


@router.post("/scenario")
async def sim_scenario_set(body: ScenarioBody, role: str = Depends(require_role("admin"))):
    if settings.device_mode != "simulate":
        return {"ok": False, "message": "当前为 real 模式，场景切换仅对 simulate 有效"}
    try:
        name = set_current_scenario(body.scenario)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": str(exc)}
    audit.log("sim", actor=role, action="scenario.switch", detail=name)
    return {"ok": True, "scenario": name, "available": AVAILABLE}

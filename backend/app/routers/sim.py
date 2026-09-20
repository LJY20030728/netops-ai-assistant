"""仿真故障场景切换路由（simulate 模式）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import settings
from app.agent.devices import VALID_SCENARIOS, get_current_scenario, set_current_scenario
from app.security import audit
from app.security.auth import require_role

router = APIRouter(prefix="/api/sim", tags=["sim"])

# 与 devices.py 的 8 个故障剧本保持一致（单一事实来源）
AVAILABLE = list(VALID_SCENARIOS)


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

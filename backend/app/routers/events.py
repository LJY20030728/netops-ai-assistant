"""审计事件时间线路由。"""
import json

from fastapi import APIRouter, Depends

from app.config import DATA_DIR
from app.security.auth import require_role

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/timeline")
async def events_timeline(limit: int = 50, role: str = Depends(require_role("viewer"))):
    limit = max(1, min(int(limit), 500))  # 边界：非法 limit 收敛到 [1,500]
    path = DATA_DIR / "audit.jsonl"
    events: list[dict] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-max(limit * 4, 300):]:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    events = events[-limit:][::-1]
    return {"events": events, "count": len(events)}

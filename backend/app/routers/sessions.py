"""多会话管理路由。"""
from fastapi import APIRouter, Depends

from app import session_store
from app.security import audit
from app.security.auth import require_role

router = APIRouter(prefix="/api", tags=["sessions"])


@router.get("/sessions")
async def list_sessions(role: str = Depends(require_role("viewer"))):
    return {"ok": True, "sessions": session_store.list_sessions(limit=50)}


@router.get("/session/{session_id}")
async def session_get(session_id: str, role: str = Depends(require_role("viewer"))):
    try:
        msgs = session_store.load(session_id)
    except ValueError:
        return {"ok": False, "message": "非法 session_id"}
    return {"ok": True, "session_id": session_id, "messages": msgs}


@router.delete("/session/{session_id}")
async def session_delete(session_id: str, role: str = Depends(require_role("operator"))):
    try:
        p = session_store._path(session_id)
    except ValueError:
        return {"ok": False, "message": "非法 session_id"}
    if not p.exists():
        return {"ok": False, "message": "会话不存在"}
    p.unlink()
    audit.log("session", actor=role, action="session.delete", detail=session_id)
    return {"ok": True}

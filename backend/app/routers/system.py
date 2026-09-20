"""健康检查与认证状态路由。"""
import os
import time
from fastapi import APIRouter, Request

from app.config import settings
from app.rag import store as kb_store
from app.security import audit
from app.security.auth import resolve_auth

router = APIRouter(tags=["system"])
_STARTED_AT = time.time()  # 进程启动时间，用于 /api/health 暴露单进程边界


@router.get("/api/health")
async def health():
    from app.agent.devices import get_current_scenario
    return {
        "status": "ok",
        "service": "netops-assistant",
        "version": "0.7.1",
        "model": settings.zhipu_model,
        "embedding_model": settings.zhipu_embedding_model,
        "rerank_enabled": settings.rerank_enabled,
        "device_mode": settings.device_mode,
        "sim_scenario": get_current_scenario() if settings.device_mode == "simulate" else None,
        "mock": settings.mock_llm,
        "key_configured": bool(settings.zhipu_api_key),
        "process": {"pid": os.getpid(), "started_at": round(_STARTED_AT, 1), "workers": 1},
        "kb_chunks": kb_store.count(),
        "security": {
            "auth_enabled": settings.auth_enabled,
            "rate_limit_per_min": settings.rate_limit_per_min,
            "audit_enabled": settings.audit_enabled,
            "audit_count": audit.count(),
        },
    }


@router.get("/api/system/metrics")
async def system_metrics():
    from app.metrics import summary
    return {"ok": True, "summary": summary(100)}


@router.get("/api/auth/me")
async def auth_me(request: Request):
    authenticated, role = resolve_auth(request)
    return {
        "auth_enabled": settings.auth_enabled,
        "authenticated": authenticated,
        "role": role,
        "roles": ["viewer", "operator", "admin"],
        "hint": "AUTH_ENABLED=false（演示）时默认视为 admin；启用后需 Authorization: Bearer <token>",
    }

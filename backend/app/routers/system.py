"""健康检查与认证状态路由。"""
import json
import os
import time
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.config import KB_DIR, settings, user_config_path
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


class ConfigSaveBody(BaseModel):
    zhipu_api_key: str = ""
    zhipu_model: str = "glm-4-flash"
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    kb_dir: str = ""


@router.get("/api/config/get")
async def config_get():
    """返回当前配置（key 打码，不返回完整值）。"""
    key = settings.zhipu_api_key
    masked = ""
    if key:
        masked = key[:6] + "..." + key[-4:] if len(key) > 12 else "***"
    return {
        "ok": True,
        "zhipu_model": settings.zhipu_model,
        "zhipu_base_url": settings.zhipu_base_url,
        "key_masked": masked,
        "key_configured": bool(key),
        "kb_dir": str(KB_DIR),
    }


@router.post("/api/config/save")
async def config_save(body: ConfigSaveBody):
    """用户在设置页保存配置，写入 %APPDATA%/NetOpsAssistant/config.json。

    注意：保存后需要重启后端进程才生效（因为 settings 是启动时加载的）。
    前端会在保存后提示用户重启。
    """
    p = user_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # 读现有配置
    try:
        old = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        old = {}
    # key 为空表示不修改
    if body.zhipu_api_key.strip():
        old["ZHIPU_API_KEY"] = body.zhipu_api_key.strip()
    old["ZHIPU_MODEL"] = body.zhipu_model.strip() or "glm-4-flash"
    old["ZHIPU_BASE_URL"] = body.zhipu_base_url.strip() or "https://open.bigmodel.cn/api/paas/v4"
    if body.kb_dir.strip():
        old["KB_DIR"] = body.kb_dir.strip()
    p.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
    # 热加载：直接更新内存中的 settings，不用重启进程
    if body.zhipu_api_key.strip():
        settings.zhipu_api_key = body.zhipu_api_key.strip()
    settings.zhipu_model = body.zhipu_model.strip() or "glm-4-flash"
    settings.zhipu_base_url = body.zhipu_base_url.strip() or "https://open.bigmodel.cn/api/paas/v4"
    return {
        "ok": True,
        "message": "已保存并生效。",
        "path": str(p),
    }

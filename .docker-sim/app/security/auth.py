"""轻量 RBAC 认证：Bearer Token → 角色。

角色与权限：
- viewer  （只读问答）：可对话；Agent 仅允许 search_runbook，禁止设备工具/入库；
- operator（只读设备操作）：viewer + 可调用只读设备工具（命令/ping/tracert）；
- admin   （管理）：operator + 知识库入库等管理操作。

auth_enabled=false（默认，本地演示）：信任所有调用按 admin 处理；
auth_enabled=true：需 Authorization: Bearer <token>，token 与角色由环境变量
API_TOKENS（JSON：{"<token>":"viewer|operator|admin"}）配置。
"""
from fastapi import HTTPException, Request

from app.config import settings

ROLE_LEVEL = {"viewer": 0, "operator": 1, "admin": 2}


def resolve_role(request: Request) -> str:
    """从请求解析角色（不抛错）。

    auth_enabled=false（默认，本地演示）：信任所有调用，按 admin 处理，
    保证演示时入库/设备等全部能力可用；
    auth_enabled=true：无令牌或令牌无效 → viewer；有效令牌按配置映射角色。
    """
    return resolve_auth(request)[1]


def resolve_auth(request: Request) -> tuple[bool, str]:
    """返回 (是否已认证, 角色)。

    auth_enabled=false：视为已认证 admin（演示模式）；
    auth_enabled=true：无令牌/无效令牌 → (False, "viewer")。
    """
    if not settings.auth_enabled:
        return True, "admin"
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        role = settings.api_tokens.get(token)
        if role in ROLE_LEVEL:
            return True, role
    return False, "viewer"


def require_role(min_role: str):
    """FastAPI 依赖：要求角色不低于 min_role，否则 403。"""

    async def dep(request: Request) -> str:
        role = resolve_role(request)
        if ROLE_LEVEL.get(role, -1) < ROLE_LEVEL.get(min_role, 0):
            raise HTTPException(status_code=403, detail=f"权限不足：需要 {min_role} 及以上")
        return role

    return dep


def role_from_token(token: str) -> str:
    return settings.api_tokens.get(token, "viewer")

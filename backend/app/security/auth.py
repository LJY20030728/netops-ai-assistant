"""轻量 RBAC 认证：Bearer Token → 角色。

角色与权限：
- viewer  （只读问答）：可对话；Agent 仅允许 search_runbook，禁止设备工具/入库；
- operator（只读设备操作）：viewer + 可调用只读设备工具（命令/ping/tracert）；
- admin   （管理）：operator + 知识库入库等管理操作。

认证策略：
- 本机桌面应用（pywebview / 浏览器访问 127.0.0.1:8000）：loopback 来源自动信任为 admin，
  保证双击即用；
- 远程来源（非 loopback）：必须带 Authorization: Bearer <token>，token 与角色由环境变量
  API_TOKENS（JSON：{"<token>":"viewer|operator|admin"}）配置；无 token 一律按 viewer。
"""
from fastapi import HTTPException, Request

from app.config import settings

ROLE_LEVEL = {"viewer": 0, "operator": 1, "admin": 2}

# 本机可信来源（桌面应用 / 本地开发浏览器 / pytest TestClient）
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _is_loopback(request: Request) -> bool:
    return bool(request.client and request.client.host in _LOOPBACK_HOSTS)


def resolve_role(request: Request) -> str:
    """从请求解析角色（不抛错）。"""
    return resolve_auth(request)[1]


def resolve_auth(request: Request) -> tuple[bool, str]:
    """返回 (是否已认证, 角色)。

    - loopback 来源：视为已认证 admin（本地桌面应用场景）；
    - 带 Bearer token：按 API_TOKENS 映射角色；
    - 其余远程来源：未认证，按 viewer。
    """
    # 1) 显式 token 优先（远程用户可凭 token 获得更高权限）
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        role = settings.api_tokens.get(token)
        if role in ROLE_LEVEL:
            return True, role
        # token 无效：不直接信任为 viewer，继续走 loopback 判断
    # 2) 本机来源自动信任（桌面应用只监听 127.0.0.1）
    if settings.auth_enabled and _is_loopback(request):
        return True, "admin"
    # 3) 远程无有效 token
    if settings.auth_enabled:
        return False, "viewer"
    # auth_enabled=false（显式关闭时仍按旧行为 admin，保留逃生舱）
    return True, "admin"


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

"""网络运维智能助手（NetOps AI Assistant）· FastAPI 入口。

M4 版本：对话 + SSE + 智谱 GLM + 混合检索（BM25+向量+RRF+rerank）
+ Agent 设备工具调用 + 安全层（注入防护/RBAC/审计/限流）。
"""
import asyncio
import json
import re
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.config import KB_DIR, settings
from app.agent import agent as agent_runner
from app.agent.devices import get_current_scenario, get_devices, set_current_scenario
from app.llm.zhipu_client import LLMConfigError, stream_chat
from app.rag import ingest as kb_ingest
from app.rag import store as kb_store
from app.rag.retrieval import hybrid_retrieve
from app.security import audit
from app.security.auth import require_role, resolve_auth, resolve_role
from app.security.injection import is_blocked, scan_prompt_injection
from app.security.ratelimit import SlidingWindowRateLimiter

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(
    title="NetOps AI Assistant",
    description="面向网络运维场景的 AI 全栈助手",
    version="0.4.0",
)

# 本地开发允许跨域（后续接入 Vue/Vite 独立端口时也需要）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM_PROMPT = (
    "你是面向网络运维场景的 AI 助手「NetOps AI Assistant」。"
    "回答必须基于提供的【参考资料】，引用资料文件名作为依据；"
    "若参考资料不足以回答问题，明确说明『资料中没有覆盖该问题』，绝不编造。"
    "使用中文，步骤清晰、可执行。"
)

_rate_limiter = SlidingWindowRateLimiter(limit=settings.rate_limit_per_min, window=60)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000, description="用户本轮输入")
    history: list[dict] = Field(
        default_factory=list,
        description="多轮对话历史，元素形如 {'role': 'user'|'assistant', 'content': '...'}",
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_rag_context(query: str) -> tuple[str, list[dict]]:
    """混合检索知识库，返回（拼接后的参考资料, 来源列表）。"""
    hits = hybrid_retrieve(query, settings.rag_top_k)
    if not hits:
        return "", []
    sections = []
    sources = []
    for h in hits:
        src = h["metadata"].get("source", "未知来源")
        sections.append(f"[资料：{src}]\n{h['text']}")
        sources.append({"source": src, "score": round(h["score"], 3)})
    return "\n\n".join(sections), sources


# Agent 意图判定：只有"明确指向具体设备的诊断任务"才走 Agent 工具链路；
# 通用排障知识问答（"XX 不通应该检查什么 / 什么原因"）走 RAG 检索，
# 避免 Agent 在没有设备上下文时空转或凭参数化记忆编造（幻觉风险）。
_AGENT_DEVICE_NAMES = ("core-sw", "core-rtr", "fw-1")
_AGENT_ACTION = ("ping", "tracert", "trace", "display", "连通", "检查一下", "查一下", "排查", "排障", "诊断")
_AGENT_TARGET = ("交换机", "路由器", "防火墙", "端口", "接口", "邻居", "链路", "丢包")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def is_agent_intent(message: str) -> bool:
    low = message.lower()
    # ① 明确点名具体设备 → 设备诊断
    if any(d in low for d in _AGENT_DEVICE_NAMES):
        return True
    # ② 有"执行连通性/命令"动作且指向明确目标（IP 或设备对象）
    has_action = any(a in low for a in _AGENT_ACTION)
    has_target = bool(_IP_RE.search(message)) or any(t in low for t in _AGENT_TARGET)
    return has_action and has_target


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "netops-assistant",
        "version": "0.5.0",
        "model": settings.zhipu_model,
        "embedding_model": settings.zhipu_embedding_model,
        "rerank_enabled": settings.rerank_enabled,
        "device_mode": settings.device_mode,
        "sim_scenario": get_current_scenario() if settings.device_mode == "simulate" else None,
        "mock": settings.mock_llm,
        "key_configured": bool(settings.zhipu_api_key),
        "kb_chunks": kb_store.count(),
        "security": {
            "auth_enabled": settings.auth_enabled,
            "rate_limit_per_min": settings.rate_limit_per_min,
            "audit_enabled": settings.audit_enabled,
            "audit_count": audit.count(),
        },
    }


@app.get("/api/auth/me")
async def auth_me(request: Request):
    """返回当前认证状态与角色（供前端登录/角色裁剪）。"""
    authenticated, role = resolve_auth(request)
    return {
        "auth_enabled": settings.auth_enabled,
        "authenticated": authenticated,
        "role": role,
        "roles": ["viewer", "operator", "admin"],
        "hint": "AUTH_ENABLED=false（演示）时默认视为 admin；启用后需 Authorization: Bearer <token>",
    }


@app.get("/api/kb/stats")
async def kb_stats():
    return {
        "chunks": kb_store.count(),
        "kb_dir": str(KB_DIR),
        "embedding_model": settings.zhipu_embedding_model,
        "rerank_model": settings.rerank_model,
    }


@app.get("/api/devices")
async def devices_list(role: str = Depends(require_role("viewer"))):
    return {
        "mode": settings.device_mode,
        "scenario": get_current_scenario() if settings.device_mode == "simulate" else None,
        "devices": [
            {"name": d.name, "host": d.host, "role": d.role, "device_type": d.device_type}
            for d in get_devices()
        ],
    }


class ScenarioBody(BaseModel):
    scenario: str = Field(..., min_length=1, max_length=32)


@app.get("/api/sim/scenario")
async def sim_scenario_get():
    """查看当前仿真故障场景（仅 simulate 模式）。"""
    return {
        "mode": settings.device_mode,
        "scenario": get_current_scenario(),
        "available": ["flapping", "stp_loop", "arp_poison", "bgp_flap", "acl_deny"],
    }


@app.post("/api/sim/scenario")
async def sim_scenario_set(body: ScenarioBody, role: str = Depends(require_role("admin"))):
    """运行时切换仿真故障场景（仅 simulate 模式，admin）。"""
    if settings.device_mode != "simulate":
        return {"ok": False, "message": "当前为 real 模式，场景切换仅对 simulate 有效"}
    try:
        name = set_current_scenario(body.scenario)
    except Exception as exc:  # noqa: BLE001（未知场景等）
        return {"ok": False, "message": str(exc)}
    audit.log("sim", actor=role, action="scenario.switch", detail=name)
    return {"ok": True, "scenario": name, "available": ["flapping", "stp_loop", "arp_poison", "bgp_flap", "acl_deny"]}


@app.post("/api/kb/ingest")
async def kb_ingest_endpoint(role: str = Depends(require_role("admin"))):
    """重新扫描知识库目录并入库（幂等：重复入库会追加）。仅 admin。"""
    result = await asyncio.to_thread(kb_ingest.ingest_dir)
    result["total_chunks"] = kb_store.count()
    audit.log("ingest", actor=role, action="kb.ingest", detail=json.dumps(result, ensure_ascii=False))
    return result


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    async def gen():
        role = resolve_role(request)
        client_key = request.client.host if request.client else "unknown"

        # 安全①：限流（每 IP 每分钟）
        if not _rate_limiter.check(client_key):
            audit.log("chat", actor=role, action="rate_limited", detail=client_key)
            yield _sse({"type": "error", "message": "请求过于频繁，请稍后再试。"})
            return

        # 安全②：提示词注入检测
        flags = scan_prompt_injection(req.message)
        if is_blocked(flags):
            audit.log(
                "chat", actor=role, action="injection_blocked",
                detail=json.dumps({"ip": client_key, "flags": flags}, ensure_ascii=False),
            )
            yield _sse({"type": "error", "message": "检测到疑似提示词注入，请求已被安全层拦截。"})
            return

        audit.log("chat", actor=role, action="chat", detail=f"len={len(req.message)} ip={client_key}")

        try:
            # 设备/故障类问题 → Agent（可调用设备工具）；否则 → 纯 RAG 问答
            if is_agent_intent(req.message):
                async for event in agent_runner.run_agent(req.message, req.history, role=role):
                    if event.get("type") == "tool":
                        audit.log(
                            "tool", actor=role, action=event.get("tool", ""),
                            detail=json.dumps({"args": event.get("args"), "ok": event.get("ok")}, ensure_ascii=False),
                        )
                    yield _sse(event)
                return

            # 1) 混合检索（同步 API 放到线程池，避免阻塞事件循环）
            context, sources = await asyncio.to_thread(_build_rag_context, req.message)

            # 2) 组装带上下文的系统提示词
            sys_msg = {"role": "system", "content": SYSTEM_PROMPT}
            if context:
                sys_msg["content"] += f"\n\n【参考资料】\n{context}"

            messages = [sys_msg] + list(req.history) + [
                {"role": "user", "content": req.message}
            ]

            # 3) 先推送检索来源，再流式输出回答
            if sources:
                yield _sse({"type": "sources", "sources": sources})
            async for chunk in stream_chat(messages):
                yield _sse({"type": "delta", "content": chunk})
            yield _sse({"type": "done"})
        except LLMConfigError as exc:
            yield _sse({"type": "error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "message": f"服务异常：{exc}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")

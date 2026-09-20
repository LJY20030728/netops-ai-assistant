"""对话路由：SSE 流式 + RAG 检索 + Agent 工具调用。"""
import asyncio
import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.agent import agent as agent_runner
from app.llm.zhipu_client import LLMConfigError, stream_chat
from app.rag.retrieval import hybrid_retrieve
from app.security import audit
from app.security.auth import resolve_role
from app.security.injection import is_blocked, scan_prompt_injection
from app.security.ratelimit import SlidingWindowRateLimiter
from app import session_store

router = APIRouter(prefix="/api", tags=["chat"])

SYSTEM_PROMPT = (
    "你是面向网络运维场景的 AI 助手「NetOps AI Assistant」。"
    "回答必须基于提供的【参考资料】，引用资料文件名作为依据；"
    "若参考资料不足以回答问题，明确说明『资料中没有覆盖该问题』，绝不编造。"
    "使用中文，步骤清晰、可执行。"
)

_rate_limiter = SlidingWindowRateLimiter(limit=settings.rate_limit_per_min, window=60)

_AGENT_DEVICE_NAMES = ("core-sw", "core-rtr", "fw-1", "frr1", "frr2", "frr3")
_AGENT_ACTION = ("ping", "tracert", "trace", "display", "连通", "检查一下", "查一下",
                 "排查", "排障", "诊断", "演练", "注入", "故障", "恢复")
_AGENT_TARGET = ("交换机", "路由器", "防火墙", "端口", "接口", "邻居", "链路",
                 "丢包", "frr", "ospf", "bgp")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    history: list[dict] = Field(default_factory=list)
    session_id: str = Field(default="", max_length=64)

    @field_validator("message")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("消息不能为空")
        return v

    @field_validator("history")
    @classmethod
    def _bounded_history(cls, v: list[dict]) -> list[dict]:
        # 只保留最近 40 轮（user+assistant 各 40 条），防止无限膨胀打爆 token
        return v[-40:]


def is_agent_intent(message: str) -> bool:
    low = message.lower()
    if any(d in low for d in _AGENT_DEVICE_NAMES):
        return True
    has_action = any(a in low for a in _AGENT_ACTION)
    has_target = bool(_IP_RE.search(message)) or any(t in low for t in _AGENT_TARGET)
    return has_action and has_target


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_rag_context(query: str) -> tuple[str, list[dict]]:
    hits = hybrid_retrieve(query, settings.rag_top_k)
    if not hits:
        return "", []
    sections, sources = [], []
    for h in hits:
        src = h["metadata"].get("source", "未知来源")
        sections.append(f"[资料：{src}]\n{h['text']}")
        sources.append({"source": src, "score": round(h["score"], 3)})
    return "\n\n".join(sections), sources


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    async def gen():
        role = resolve_role(request)
        client_key = request.client.host if request.client else "unknown"

        if not _rate_limiter.check(client_key):
            audit.log("chat", actor=role, action="rate_limited", detail=client_key)
            yield _sse({"type": "error", "message": "请求过于频繁，请稍后再试。"})
            return

        flags = scan_prompt_injection(req.message)
        if is_blocked(flags):
            audit.log("chat", actor=role, action="injection_blocked",
                      detail=json.dumps({"ip": client_key, "flags": flags}, ensure_ascii=False))
            yield _sse({"type": "error", "message": "检测到疑似提示词注入，请求已被安全层拦截。"})
            return

        audit.log("chat", actor=role, action="chat", detail=f"len={len(req.message)} ip={client_key}")
        try:
            if req.session_id:
                session_store.append(req.session_id, "user", req.message)
        except ValueError:
            pass

        answer_parts: list[str] = []
        try:
            if is_agent_intent(req.message):
                async for event in agent_runner.run_agent(req.message, req.history, role=role):
                    if event.get("type") == "tool":
                        audit.log("tool", actor=role, action=event.get("tool", ""),
                                  detail=json.dumps({"args": event.get("args"), "ok": event.get("ok")},
                                                    ensure_ascii=False))
                    if event.get("type") == "delta":
                        answer_parts.append(event.get("content", ""))
                    yield _sse(event)
                try:
                    if req.session_id and answer_parts:
                        session_store.append(req.session_id, "assistant", "".join(answer_parts))
                except ValueError:
                    pass
                return

            context, sources = await asyncio.to_thread(_build_rag_context, req.message)
            sys_msg = {"role": "system", "content": SYSTEM_PROMPT}
            if context:
                sys_msg["content"] += f"\n\n【参考资料】\n{context}"
            messages = [sys_msg] + list(req.history) + [{"role": "user", "content": req.message}]

            if sources:
                yield _sse({"type": "sources", "sources": sources})
            # 思考中提示：让用户感知模型正在工作（LLM 生成前）
            yield _sse({"type": "thinking", "text": "思考中…"})
            async for chunk in stream_chat(messages):
                answer_parts.append(chunk)
                yield _sse({"type": "delta", "content": chunk})
            yield _sse({"type": "done"})
            try:
                if req.session_id and answer_parts:
                    session_store.append(req.session_id, "assistant", "".join(answer_parts))
            except ValueError:
                pass
        except LLMConfigError as exc:
            yield _sse({"type": "error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            # 不向用户泄露原始异常（防信息泄露）；细节进审计日志
            audit.log("chat", actor=role, action="chat_error",
                      detail=f"{type(exc).__name__}: {exc}")
            yield _sse({"type": "error", "message": "服务暂时不可用，请稍后重试或查看系统日志。"})

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive",
    })

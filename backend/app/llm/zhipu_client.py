"""LLM Provider 客户端：OpenAI 兼容协议，支持智谱 / 豆包切换。

通过 settings.llm_provider 选择：
  - zhipu  ：智谱 GLM（base_url=open.bigmodel.cn）
  - doubao ：豆包 Ark（base_url=ark.cn-beijing.volces.com）

两者都是 OpenAI Chat Completions 兼容协议，底层复用 AsyncOpenAI。
未配置 Key 或 LLM_MOCK=true 时走 mock 回复，便于本地调试。
"""
from typing import AsyncIterator

from openai import AsyncOpenAI

from app.config import settings


class LLMConfigError(RuntimeError):
    """配置缺失或错误。"""


_client: AsyncOpenAI | None = None
_active_provider: str | None = None


def _resolve_credentials() -> tuple[str, str, str]:
    """根据当前 provider 返回 (api_key, base_url, model)。"""
    provider = settings.llm_provider.lower()
    if provider == "doubao":
        if not settings.doubao_api_key:
            raise LLMConfigError(
                "未配置 DOUBAO_API_KEY：请在 backend/.env 填写，或切换 LLM_PROVIDER=zhipu。"
            )
        return settings.doubao_api_key, settings.doubao_base_url, settings.doubao_model
    # 默认 zhipu
    if not settings.zhipu_api_key:
        raise LLMConfigError(
            "未配置 ZHIPU_API_KEY：请在 backend/.env 填写智谱 API Key，"
            "或设置 LLM_MOCK=true 使用模拟模式。"
        )
    return settings.zhipu_api_key, settings.zhipu_base_url, settings.zhipu_model


def _get_client() -> AsyncOpenAI:
    global _client, _active_provider
    key, base_url, _ = _resolve_credentials()
    # provider 切换后重建 client
    if _client is None or _active_provider != settings.llm_provider:
        _client = AsyncOpenAI(api_key=key, base_url=base_url, timeout=settings.request_timeout)
        _active_provider = settings.llm_provider
    return _client


def current_model() -> str:
    """当前生效的模型名（供 /api/health 展示）。"""
    try:
        return _resolve_credentials()[2]
    except LLMConfigError:
        return settings.zhipu_model


async def _mock_stream(messages: list[dict]) -> AsyncIterator[str]:
    """模拟回复：让前端在无 Key 情况下也能看到完整流式链路。"""
    reply = (
        "【模拟模式】未配置真实 LLM API Key，当前为演示回复。\n"
        "以下为 flapping 排障示例：\n"
        "1. 查看端口状态与协商信息：show interface <port>\n"
        "2. 检查收发光功率与错误计数（CRC/Frame）\n"
        "3. 检查日志中链路协商记录\n"
        "4. 结合以上结果判断根因并给出处置建议。\n"
    )
    for i in range(0, len(reply), 6):
        yield reply[i : i + 6]


async def stream_chat(messages: list[dict], usage_out: dict | None = None) -> AsyncIterator[str]:
    """流式输出模型回复。usage_out 非空时，结束时把 {prompt_tokens, completion_tokens} 写进去。"""
    if settings.mock_llm:
        async for chunk in _mock_stream(messages):
            yield chunk
        if usage_out is not None:
            usage_out.update({"prompt_tokens": 0, "completion_tokens": 0})
        return

    _, _, model = _resolve_credentials()
    client = _get_client()
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        max_tokens=settings.max_tokens,
        temperature=settings.temperature,
        stream_options={"include_usage": True},
    )
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
        # 最后一个 chunk：choices 为空但带 usage
        if usage_out is not None and getattr(chunk, "usage", None):
            usage_out["prompt_tokens"] = chunk.usage.prompt_tokens or 0
            usage_out["completion_tokens"] = chunk.usage.completion_tokens or 0


async def complete_json(messages: list[dict], max_tokens: int = 1024) -> str:
    """非流式调用，返回模型回复原文（供 Agent 决策解析）。"""
    if settings.mock_llm:
        return '{"action":"finish"}'

    _, _, model = _resolve_credentials()
    client = _get_client()
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""

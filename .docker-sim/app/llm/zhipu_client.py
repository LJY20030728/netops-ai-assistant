"""智谱 GLM 大模型客户端：OpenAI 兼容协议，支持流式输出。

- 配置了 ZHIPU_API_KEY 时调用真实智谱 GLM 模型。
- 未配置 Key 且 LLM_MOCK=true 时返回模拟回复，方便本地调试。
"""
from typing import AsyncIterator

from openai import AsyncOpenAI

from app.config import settings


class LLMConfigError(RuntimeError):
    """配置缺失或错误。"""


_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.zhipu_api_key,
            base_url=settings.zhipu_base_url,
            timeout=settings.request_timeout,
        )
    return _client


async def _mock_stream(messages: list[dict]) -> AsyncIterator[str]:
    """模拟回复：让前端在无 Key 情况下也能看到完整的流式链路。"""
    reply = (
        "【模拟模式】未配置智谱 API Key，当前为演示回复，配置 ZHIPU_API_KEY 后接入真实 GLM 模型。\n\n"
        "以「端口 flapping 排查」为例，建议按以下步骤进行：\n"
        "1. 查看端口状态与协商信息：show interface <port> / show interface counters\n"
        "2. 检查收发光功率与错误计数（CRC/Frame 等）。\n"
        "3. 检查日志中的链路协商记录：show logging | include link\n"
        "4. 结合以上结果判断根因（光衰、硬件、配置或对端问题）并给出处置建议。\n\n"
        "—— 该流程后续将由 RAG 知识检索 + Agent 工具调用自动完成。"
    )
    step = 6
    for i in range(0, len(reply), step):
        yield reply[i : i + step]


async def stream_chat(messages: list[dict]) -> AsyncIterator[str]:
    """以流式方式逐块产出模型回复文本。"""
    if settings.mock_llm:
        async for chunk in _mock_stream(messages):
            yield chunk
        return

    if not settings.zhipu_api_key:
        raise LLMConfigError(
            "未配置 ZHIPU_API_KEY：请在 backend/.env 中填写智谱 API Key；"
            "或临时设置 LLM_MOCK=true 使用模拟模式。"
        )

    client = _get_client()
    stream = await client.chat.completions.create(
        model=settings.zhipu_model,
        messages=messages,
        stream=True,
        max_tokens=settings.max_tokens,
        temperature=settings.temperature,
    )
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


async def complete_json(messages: list[dict], max_tokens: int = 1024) -> str:
    """非流式调用，返回模型回复原文（供 Agent 决策解析，应为 JSON 文本）。

    未配置 Key 时返回一个固定的模拟决策 JSON（finish），保证无 Key 也能跑通 Agent 循环。
    """
    if settings.mock_llm or not settings.zhipu_api_key:
        return '{"action":"finish"}'

    client = _get_client()
    resp = await client.chat.completions.create(
        model=settings.zhipu_model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""

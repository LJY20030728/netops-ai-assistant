"""智谱 embedding API 封装（同步调用，供入库与检索使用）。

- 配置了 ZHIPU_API_KEY 时调用智谱 embedding-3。
- 未配置 Key（或 LLM_MOCK=true）时使用本地哈希嵌入（确定性、无外部依赖），
  保证无 Key 也能跑通整条 RAG 链路，便于开发与自测。
"""
import hashlib
import math

from openai import OpenAI

from app.config import settings

_client: OpenAI | None = None

_LOCAL_DIM = 256


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.zhipu_api_key,
            base_url=settings.zhipu_base_url,
            timeout=settings.request_timeout,
        )
    return _client


def _local_embed(text: str, dim: int = _LOCAL_DIM) -> list[float]:
    """无 Key 时的降级嵌入：字符 n-gram 哈希，确定性向量。"""
    vec = [0.0] * dim
    for i in range(len(text)):
        grams = text[max(0, i - 2) : i + 1]
        h = hashlib.md5(grams.encode()).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if h[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if settings.mock_llm or not settings.zhipu_api_key:
        return [_local_embed(t) for t in texts]
    client = _get_client()
    out: list[list[float] | None] = [None] * len(texts)
    # 智谱 embedding 单次请求最多 64 条，按 32 分批以留余量
    batch_size = 32
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        resp = client.embeddings.create(
            model=settings.zhipu_embedding_model,
            input=batch,
        )
        for d in resp.data:
            out[start + d.index] = d.embedding
    return [v for v in out if v is not None]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]

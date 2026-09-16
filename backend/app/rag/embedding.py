"""文本嵌入：优先本地 bge-small-zh-v1.5（免费、离线、语义向量）。

- 配置 ZHIPU_EMBEDDING_MODEL=bge 时走本地模型（推荐，免费）
- 配置 ZHIPU_EMBEDDING_MODEL=local 时走哈希降级（无依赖）
- 其他值（如 embedding-3）走智谱 API
"""
import hashlib
import math
import os

from openai import OpenAI

from app.config import settings

_client: OpenAI | None = None
_bge_model = None
_BGE_NAME = "BAAI/bge-small-zh-v1.5"

_LOCAL_DIM = 512  # bge-small-zh 输出 512 维


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.zhipu_api_key,
            base_url=settings.zhipu_base_url,
            timeout=settings.request_timeout,
        )
    return _client


def _get_bge():
    """懒加载 bge 模型（首次调用下载 ~100MB）。"""
    global _bge_model
    if _bge_model is None:
        # 国内镜像加速
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        from sentence_transformers import SentenceTransformer
        _bge_model = SentenceTransformer(_BGE_NAME, device="cpu")
    return _bge_model


def _local_embed(text: str, dim: int = _LOCAL_DIM) -> list[float]:
    """哈希降级：字符 n-gram，确定性向量（不保证语义）。"""
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
    model_name = (settings.zhipu_embedding_model or "").lower()

    # 1. bge 本地语义模型
    if model_name in ("bge", "bge-small", "bge-small-zh", "bge-small-zh-v1.5"):
        m = _get_bge()
        embs = m.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [e.tolist() for e in embs]

    # 2. 哈希降级
    if (
        settings.mock_llm
        or not settings.zhipu_api_key
        or not model_name
        or model_name in ("local", "none", "hash")
    ):
        return [_local_embed(t) for t in texts]

    # 3. 智谱 API
    client = _get_client()
    out: list[list[float] | None] = [None] * len(texts)
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

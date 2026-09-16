"""向量库门面（facade）：业务代码只依赖本模块的同名函数。

实现细节在 app.rag.vector_base（VectorBackend 接口 + NumpyVectorStore / QdrantVectorStore），
通过 settings.vector_backend 选择后端，平滑切换无需改动调用方。
"""
from app.rag.vector_base import get_backend

__all__ = ["count", "add_chunks", "search", "reset", "records", "get_backend"]


def count() -> int:
    return get_backend().count()


def add_chunks(chunks: list[dict]) -> int:
    return get_backend().add_chunks(chunks)


def search(query: str, top_k: int = 5) -> list[dict]:
    return get_backend().search(query, top_k)


def reset() -> None:
    get_backend().reset()


def records() -> list[dict]:
    return get_backend().records()

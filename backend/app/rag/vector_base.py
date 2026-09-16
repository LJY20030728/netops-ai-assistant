"""向量库抽象层：可插拔后端（numpy / qdrant）。

设计动机（简历可讲）：
- 定义 VectorBackend 接口（count / add_chunks / search），业务代码只依赖接口；
- 默认 NumpyVectorStore（自研：numpy 余弦 + meta.json/vectors.npy 持久化，零重型依赖）；
- QdrantVectorStore 为可选适配器：安装 qdrant-client 并在 .env 设 VECTOR_BACKEND=qdrant 后启用，
  无需改动检索/入库调用方，实现"数据规模增长时平滑迁移"。
"""
from abc import ABC, abstractmethod

import numpy as np

from app.config import DATA_DIR
from app.rag.embedding import embed_texts

META_FILE = DATA_DIR / "meta.json"
VEC_FILE = DATA_DIR / "vectors.npy"


class VectorBackend(ABC):
    """向量存储/检索接口。"""

    @abstractmethod
    def count(self) -> int:
        ...

    @abstractmethod
    def add_chunks(self, chunks: list[dict]) -> int:
        """chunks: [{id, text, metadata}]，按 id 幂等去重，返回新增条数。"""

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """余弦/向量检索，返回 [{id, text, metadata, score}]。"""

    @abstractmethod
    def reset(self) -> None:
        """清空全部数据（测试用）。"""

    @abstractmethod
    def records(self) -> list[dict]:
        """返回全部记录 [{id, text, metadata}]（供 BM25 索引等全量遍历）。"""


class NumpyVectorStore(VectorBackend):
    """自研实现：numpy 余弦相似度 + 本地文件持久化。"""

    def __init__(self) -> None:
        self._records: list[dict] | None = None

    def _load(self) -> list[dict]:
        if self._records is not None:
            return self._records
        if META_FILE.exists() and VEC_FILE.exists():
            import json

            metas = json.loads(META_FILE.read_text(encoding="utf-8"))
            vecs = np.load(VEC_FILE)
            self._records = [
                {
                    "id": m["id"],
                    "text": m["text"],
                    "metadata": m["metadata"],
                    "vector": vecs[i].tolist(),
                }
                for i, m in enumerate(metas)
            ]
        else:
            self._records = []
        return self._records

    def _save(self) -> None:
        import json

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        metas = [
            {"id": r["id"], "text": r["text"], "metadata": r["metadata"]}
            for r in self._records or []
        ]
        vecs = (
            np.array([r["vector"] for r in self._records])
            if self._records
            else np.zeros((0, 0))
        )
        META_FILE.write_text(
            json.dumps(metas, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        np.save(VEC_FILE, vecs)

    def count(self) -> int:
        return len(self._load())

    def add_chunks(self, chunks: list[dict]) -> int:
        recs = self._load()
        by_id = {r["id"]: r for r in recs}
        # 幂等 + 内容变更检测：同 id 且文本与元数据均一致→跳过；
        # 文本或元数据任一变化→替换（向量重算）。
        # 注意：metadata 变化（如 layer/alarm_type 升级）也必须触发替换，
        # 否则历史记录永远停留在旧元数据（历史 bug：仅比较 text 导致元数据不更新）。
        new_chunks: list[dict] = []
        for c in chunks:
            old = by_id.get(c["id"])
            if old is None:
                new_chunks.append(c)
            elif old["text"] != c["text"] or old.get("metadata") != c.get("metadata"):
                new_chunks.append(c)
        if not new_chunks:
            return 0
        vectors = embed_texts([c["text"] for c in new_chunks])
        # 注意：必须原地修改 self._records（_load 返回的引用），
        # 重新绑定局部 recs 会导致 _save() 写回旧数据（入库替换失效的历史 bug）。
        removed = {c["id"] for c in new_chunks}
        self._records = [r for r in recs if r["id"] not in removed]
        for c, v in zip(new_chunks, vectors):
            self._records.append(
                {"id": c["id"], "text": c["text"], "metadata": c["metadata"], "vector": v}
            )
        self._save()
        return len(new_chunks)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        recs = self._load()
        if not recs:
            return []
        q = np.array(embed_texts([query])[0])
        mat = np.array([r["vector"] for r in recs])
        sims = mat @ q / (np.linalg.norm(mat, axis=1) * np.linalg.norm(q) + 1e-12)
        order = np.argsort(-sims)[:top_k]
        return [
            {
                "id": recs[i]["id"],
                "text": recs[i]["text"],
                "metadata": recs[i]["metadata"],
                "score": float(sims[i]),
            }
            for i in order
        ]

    def reset(self) -> None:
        self._records = []
        self._save()

    def records(self) -> list[dict]:
        return [
            {"id": r["id"], "text": r["text"], "metadata": r["metadata"]}
            for r in self._load()
        ]


class QdrantVectorStore(VectorBackend):
    """Qdrant 适配器（按需启用）：.env 设 VECTOR_BACKEND=qdrant，且 pip install qdrant-client。

    使用本地磁盘模式（path=DATA_DIR/qdrant），不依赖 Qdrant 服务进程，便于演示与测试。
    """

    def __init__(self) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "VECTOR_BACKEND=qdrant 但未安装 qdrant-client。请执行：pip install qdrant-client"
            ) from exc
        self._client = QdrantClient(path=str(DATA_DIR / "qdrant"))
        self._VectorParams = VectorParams
        self._Distance = Distance
        self._COLLECTION = "kb_chunks"
        self._dim = 256  # 本地哈希嵌入维度；使用真实 embedding-3 时按首个向量维度重建
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        cols = self._client.get_collections().collections
        if not any(c.name == self._COLLECTION for c in cols):
            self._client.create_collection(
                collection_name=self._COLLECTION,
                vectors_config=self._VectorParams(
                    size=self._dim, distance=self._Distance.COSINE
                ),
            )

    def count(self) -> int:
        return self._client.count(self._COLLECTION, exact=True).count

    def add_chunks(self, chunks: list[dict]) -> int:
        from qdrant_client.models import PointStruct

        existing = {p.id for p in self._client.scroll(
            self._COLLECTION, limit=10000, with_vectors=False
        )[0]}
        new_chunks = [c for c in chunks if c["id"] not in existing]
        if not new_chunks:
            return 0
        vectors = embed_texts([c["text"] for c in new_chunks])
        points = [
            PointStruct(
                id=hash(c["id"]) % (2**63),
                vector=v,
                payload={"text": c["text"], "metadata": c["metadata"]},
            )
            for c, v in zip(new_chunks, vectors)
        ]
        self._client.upsert(self._COLLECTION, points=points)
        return len(new_chunks)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        from qdrant_client.models import Filter

        q = embed_texts([query])[0]
        hits = self._client.search(
            collection_name=self._COLLECTION,
            query_vector=q,
            limit=top_k,
            query_filter=Filter(),
        )
        return [
            {
                "id": str(h.id),
                "text": h.payload.get("text", ""),
                "metadata": h.payload.get("metadata", {}),
                "score": float(h.score),
            }
            for h in hits
        ]

    def reset(self) -> None:
        self._client.delete_collection(self._COLLECTION)
        self._ensure_collection()

    def records(self) -> list[dict]:
        pts, _ = self._client.scroll(self._COLLECTION, limit=10000, with_vectors=False)
        return [
            {"id": str(p.id), "text": p.payload.get("text", ""), "metadata": p.payload.get("metadata", {})}
            for p in pts
        ]


# 模块级单例（供 store facade 复用缓存）
_numpy_store = NumpyVectorStore()
_qdrant_store: QdrantVectorStore | None = None


def get_backend() -> VectorBackend:
    from app.config import settings

    if settings.vector_backend == "qdrant":
        global _qdrant_store
        if _qdrant_store is None:
            _qdrant_store = QdrantVectorStore()
        return _qdrant_store
    return _numpy_store

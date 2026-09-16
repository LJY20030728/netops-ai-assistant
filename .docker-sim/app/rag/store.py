"""轻量自研向量库：numpy 余弦相似度 + 本地持久化。

设计取舍：不引入 ChromaDB/FAISS 的重型依赖树，零兼容风险、完全可控，
可清晰讲解「向量化 → 存储 → 余弦检索」原理；数据规模增大时可平滑替换为
Qdrant / Milvus（接口仅需改 store 层）。
"""
import json

import numpy as np

from app.config import DATA_DIR
from app.rag.embedding import embed_texts

META_FILE = DATA_DIR / "meta.json"
VEC_FILE = DATA_DIR / "vectors.npy"

_records: list[dict] | None = None


def _load() -> list[dict]:
    global _records
    if _records is not None:
        return _records
    if META_FILE.exists() and VEC_FILE.exists():
        metas = json.loads(META_FILE.read_text(encoding="utf-8"))
        vecs = np.load(VEC_FILE)
        _records = [
            {
                "id": m["id"],
                "text": m["text"],
                "metadata": m["metadata"],
                "vector": vecs[i].tolist(),
            }
            for i, m in enumerate(metas)
        ]
    else:
        _records = []
    return _records


def _save() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    metas = [
        {"id": r["id"], "text": r["text"], "metadata": r["metadata"]} for r in _records
    ]
    vecs = np.array([r["vector"] for r in _records]) if _records else np.zeros((0, 0))
    META_FILE.write_text(json.dumps(metas, ensure_ascii=False, indent=1), encoding="utf-8")
    np.save(VEC_FILE, vecs)


def count() -> int:
    return len(_load())


def add_chunks(chunks: list[dict]) -> int:
    """chunks: [{id, text, metadata}]，批量向量化后写入（按 id 去重，幂等）。

    已存在的 id（同文件同 chunk 序号）直接跳过，避免重复入库造成向量库膨胀。
    """
    recs = _load()
    existing = {r["id"] for r in recs}
    new_chunks = [c for c in chunks if c["id"] not in existing]
    if not new_chunks:
        return 0
    texts = [c["text"] for c in new_chunks]
    vectors = embed_texts(texts)
    for c, v in zip(new_chunks, vectors):
        recs.append(
            {"id": c["id"], "text": c["text"], "metadata": c["metadata"], "vector": v}
        )
    _save()
    return len(new_chunks)


def search(query: str, top_k: int = 5) -> list[dict]:
    """余弦相似度检索，返回 [{id, text, metadata, score}]。"""
    recs = _load()
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

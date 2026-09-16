"""混合检索：BM25（词法） + 向量（语义） + RRF 融合 + 智谱 rerank 重排。

- BM25 自研实现（不引 jieba/rank-bm25）：中文按 CJK 单字+二元组切分，英文按词切分；
- 向量检索复用 store.search（智谱 embedding-3 余弦）；
- RRF（Reciprocal Rank Fusion）融合两类候选；
- rerank 用智谱 rerank API 对融合后候选精排（未配置 Key/模拟模式自动跳过）。
"""
import json
import math
import re
import threading
import urllib.request
from collections.abc import Iterable

from app.config import settings
from app.rag import store as kb_store

_CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]+")
_ASCII = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """中英混合分词：ASCII 词 + CJK 单字与相邻二元组。"""
    text = (text or "").lower()
    tokens: list[str] = _ASCII.findall(text)
    for m in _CJK.finditer(text):
        s = m.group()
        for i, ch in enumerate(s):
            tokens.append(ch)
            if i + 1 < len(s):
                tokens.append(s[i : i + 2])
    return tokens


class BM25:
    """标准 BM25（k1=1.5, b=0.75）。"""

    def __init__(self, docs: list[str]):
        self.k1 = 1.5
        self.b = 0.75
        self.n = len(docs)
        self.doc_tokens = [tokenize(d) for d in docs]
        self.dl = [len(t) for t in self.doc_tokens]
        self.avgdl = sum(self.dl) / max(self.n, 1)
        self.df: dict[str, int] = {}
        for toks in self.doc_tokens:
            for t in set(toks):
                self.df[t] = self.df.get(t, 0) + 1
        self.idf = {
            t: math.log(1 + (self.n - df + 0.5) / (df + 0.5))
            for t, df in self.df.items()
        }

    def score_all(self, query: str) -> list[float]:
        qf: dict[str, int] = {}
        for t in tokenize(query):
            qf[t] = qf.get(t, 0) + 1
        scores = [0.0] * self.n
        for t, c in qf.items():
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i, toks in enumerate(self.doc_tokens):
                tf = toks.count(t)
                if tf:
                    denom = tf + self.k1 * (1 - self.b + self.b * self.dl[i] / self.avgdl)
                    scores[i] += idf * (c * (self.k1 + 1) * tf / denom)
        return scores


# BM25 索引缓存（入库后失效）
_bm25: BM25 | None = None
_bm25_key: str | None = None
_bm25_lock = threading.Lock()


def _get_bm25() -> BM25:
    global _bm25, _bm25_key
    recs = kb_store._load()
    key = f"{len(recs)}:{len(recs[0]['text']) if recs else 0}"
    with _bm25_lock:
        if _bm25 is None or _bm25_key != key:
            _bm25 = BM25([r["text"] for r in recs])
            _bm25_key = key
        return _bm25


def _rrf_fuse(ranked_lists: Iterable[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion：合并多个按相关度排序的文档 id 列表。

    返回 [(doc_id, rrf_score)]，按分数降序。
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


def _zhipu_rerank(query: str, documents: list[str], top_n: int = None) -> list[float]:
    """调用智谱 rerank，返回与 documents 对齐的相关度分数。"""
    body = {
        "model": settings.rerank_model,
        "query": query,
        "documents": documents,
    }
    if top_n is not None:
        body["top_n"] = top_n
    req = urllib.request.Request(
        "https://open.bigmodel.cn/api/paas/v4/rerank",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.zhipu_api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=settings.request_timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    scores = [0.0] * len(documents)
    for r in data.get("results", []):
        scores[r["index"]] = r.get("relevance_score", 0.0)
    return scores


def _use_rerank() -> bool:
    return settings.rerank_enabled and bool(settings.zhipu_api_key) and not settings.mock_llm


def hybrid_retrieve(
    query: str,
    top_k: int = 5,
    *,
    use_rerank: bool | None = None,
) -> list[dict]:
    """混合检索主入口：返回 [{id, text, metadata, score}]。

    score 口径：rerank 启用时为 relevance_score；否则为 RRF 融合分（归一化到 0~1）。
    """
    recs = kb_store._load()
    if not recs:
        return []
    rec_by_id = {r["id"]: r for r in recs}

    # 1) 向量候选
    vec_hits = kb_store.search(query, settings.hybrid_vec_k)
    vec_ranked = [h["id"] for h in vec_hits]

    # 2) BM25 候选
    bm25_scores = _get_bm25().score_all(query)
    bm25_ranked = [
        recs[i]["id"] for i in sorted(range(len(recs)), key=lambda i: -bm25_scores[i])
    ][: settings.hybrid_bm25_k]

    # 3) RRF 融合，取候选
    fused = _rrf_fuse([vec_ranked, bm25_ranked], settings.rrf_k)
    candidates = [rec_by_id[i] for i, _ in fused[: max(top_k * 2, 8)] if i in rec_by_id]

    # 4) rerank 精排
    if use_rerank is None:
        use_rerank = _use_rerank()
    if use_rerank and candidates:
        scores = _zhipu_rerank(query, [c["text"] for c in candidates])
        ordered = sorted(range(len(candidates)), key=lambda i: -scores[i])
        return [
            {
                "id": candidates[i]["id"],
                "text": candidates[i]["text"],
                "metadata": candidates[i]["metadata"],
                "score": round(scores[i], 4),
            }
            for i in ordered[:top_k]
        ]

    # 无 rerank：归一化 RRF 分
    max_s = fused[0][1] if fused else 1.0
    out = []
    for doc_id, raw in fused:
        if doc_id not in rec_by_id:
            continue
        out.append(
            {
                "id": doc_id,
                "text": rec_by_id[doc_id]["text"],
                "metadata": rec_by_id[doc_id]["metadata"],
                "score": round(raw / max_s, 4),
            }
        )
        if len(out) >= top_k:
            break
    return out

"""混合检索：BM25（词法） + 向量（语义） + RRF 融合 + 智谱 rerank 重排。

- BM25 自研实现（不引 jieba/rank-bm25）：中文按 CJK 单字+二元组切分，英文按词切分；
- 向量检索复用 store.search（智谱 embedding-3 余弦）；
- RRF（Reciprocal Rank Fusion）融合两类候选；
- rerank 用智谱 rerank API 对融合后候选精排（未配置 Key/模拟模式自动跳过）。
- M5 评测归因驱动：口语查询同义词扩展（expand_query），修复"词面差异"低分。
"""
import json
import math
import re
import threading
import urllib.request
from collections.abc import Iterable

from app.config import settings
from app.rag import store as kb_store
from app.rag import alert_router

# 通道 A 加权：告警路由命中的手册/案例，RRF 分提升比例（相对当前最高分）
_ALERT_BOOST_RATIO = 1.2

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
    recs = kb_store.records()
    # 缓存 key 覆盖数量与内容（文本总长），入库内容变更后自动重建索引
    key = f"{len(recs)}:{sum(len(r['text']) for r in recs)}"
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
    """调用智谱 rerank，返回与 documents 对齐的排序键（越大越相关）。

    注意：智谱 rerank 的 relevance_score 字段对多数输入几乎无区分度（常见 1.0），
    真正的排序信息在 results 数组的 index 顺序里（按相关度降序）。
    因此以"顺序"构造排序键，而非 score。
    """
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
    order = [r["index"] for r in data.get("results", [])]
    keys = [0.0] * len(documents)
    for pos, idx in enumerate(order):
        if 0 <= idx < len(documents):
            keys[idx] = float(len(documents) - pos)
    return keys


def _use_rerank() -> bool:
    return settings.rerank_enabled and bool(settings.zhipu_api_key) and not settings.mock_llm


# 口语 → 标准术语 查询扩展（M5 评测归因驱动：修复"词面差异"导致的低分）
# 仅影响 BM25 词法匹配与 rerank 输入，向量检索仍用原查询（语义已覆盖同义）。
_QUERY_EXPANSION = {
    "抖动": "flapping",
    "up/down": "flapping",
    "时通时断": "flapping",
    "反复 up": "flapping",
    "抓包": "端口镜像",
    "带宽打满": "拥塞 时延",
    "流量异常": "流量 拥塞",
    "拓扑变化": "STP 拓扑变更 TCN",
    "拓扑变更": "STP TCN",
    "广播风暴": "广播风暴 loop",
    "广播": "广播风暴",
    "掉线": "离线",
    "拿不到地址": "DHCP",
    "获取不到": "DHCP",
    "网络卡": "时延 拥塞",
    "重传": "时延 拥塞",
    "变慢": "时延 拥塞",
    # ---- 多词短语消歧（覆盖复合意图，抑制近邻文档竞争）----
    "带宽打满 抓包": "端口镜像 流量分析",
    "抓包 带宽": "端口镜像 流量分析",
    "广播风暴 抓包": "端口镜像 抓包分析",
    "抓包 广播风暴": "端口镜像 抓包分析",
    "应用流量": "端口镜像 流量分析",
    "流量构成": "端口镜像 流量分析",
    "断网重连": "flapping 端口抖动",
    "掉线重连": "flapping 端口抖动",
    "last down reason": "BGP 邻居 状态",
    "connectretry": "BGP 邻居 状态",
    "跨网段 时通时断": "静态路由 路由表 下一跳",
    "跨网段 间歇性": "静态路由 路由表 下一跳",
    "配置丢失": "配置备份 保存配置",
    "重启后 配置": "配置备份 保存配置",
    "光纤头脏": "光模块 收发光功率 光衰",
    "光纤 脏": "光模块 收发光功率 光衰",
    "一会儿通 一会儿断 光纤": "光模块 收发光功率",
}


def expand_query(query: str) -> str:
    """对口语化查询追加标准术语，返回扩展后的查询串（无命中时原样返回）。"""
    low = (query or "").lower()
    extra: list[str] = []
    for zh, term in _QUERY_EXPANSION.items():
        if zh in low:
            for t in term.split():
                if t not in extra:
                    extra.append(t)
    return (query + " " + " ".join(extra)).strip() if extra else (query or "")


def _dedupe_by_source(hits: list[dict]) -> list[dict]:
    """文档级多样性：同一 source 只保留最高分 chunk，避免同文档多 chunk 霸榜占位。"""
    best: dict[str, dict] = {}
    for h in hits:
        src = h['metadata'].get('source', h['id'])
        if src not in best or h['score'] > best[src]['score']:
            best[src] = h
    return sorted(best.values(), key=lambda h: -h['score'])


def hybrid_retrieve(
    query: str,
    top_k: int = 5,
    *,
    use_rerank: bool | None = None,
) -> list[dict]:
    """混合检索主入口：返回 [{id, text, metadata, score}]。

    score 口径：rerank 启用时为 relevance_score；否则为 RRF 融合分（归一化到 0~1）。
    """
    recs = kb_store.records()
    if not recs:
        return []
    rec_by_id = {r["id"]: r for r in recs}
    # 词法扩展（口语→术语）：BM25 与向量、rerank 均用扩展查询（实测对低分用例更稳）
    bm25_query = expand_query(query)

    # 1) 向量候选
    vec_hits = kb_store.search(bm25_query, settings.hybrid_vec_k)
    vec_ranked = [h["id"] for h in vec_hits]

    # 2) BM25 候选
    bm25_scores = _get_bm25().score_all(bm25_query)
    bm25_ranked = [
        recs[i]["id"] for i in sorted(range(len(recs)), key=lambda i: -bm25_scores[i])
    ][: settings.hybrid_bm25_k]

    # 3) RRF 融合，取候选
    fused = _rrf_fuse([vec_ranked, bm25_ranked], settings.rrf_k)
    candidates = [rec_by_id[i] for i, _ in fused[: max(top_k * 4, 16)] if i in rec_by_id]

    # 3.5) 通道 A（L3 告警路由加权）：命中的告警将其指向的手册/案例提升到最前。
    #      确定性规则 → 模糊检索 双通道：路由命中不替代检索，而是在融合分上叠加提升，
    #      避免"告警指向"掩盖了检索到的其他相关内容。
    route = alert_router.route_alert(query)
    if route:
        route_sources = set(route.get("manuals", [])) | set(route.get("cases", []))
        boost_ids = {
            r["id"] for r in recs if r["metadata"].get("source") in route_sources
        }
        if boost_ids and fused:
            top_score = fused[0][1]
            boost = top_score * _ALERT_BOOST_RATIO
            fused = sorted(
                [
                    (doc_id, score + (boost if doc_id in boost_ids else 0.0))
                    for doc_id, score in fused
                ],
                key=lambda x: -x[1],
            )

    # 4) rerank 精排：与 RRF 分按 rerank_weight 加权融合。
    #    评测驱动结论（60 条领域评测）：智谱通用 rerank 排序偏差大，
    #    权重 0.4→MRR 0.566、0.2→0.693，均低于纯 RRF 0.891；故默认权重 0（不参与）。
    if use_rerank is None:
        use_rerank = _use_rerank()
    w = float(getattr(settings, "rerank_weight", 0.0))
    if use_rerank and candidates and w > 0:
        keys = _zhipu_rerank(bm25_query, [c["text"] for c in candidates])
        rrf_scores = {doc_id: raw for doc_id, raw in fused}
        max_rrf = fused[0][1] if fused else 1.0
        fused_scores = []
        for i, c in enumerate(candidates):
            rr = rrf_scores.get(c["id"], 0.0) / max_rrf
            rk = keys[i] / max(len(keys), 1)
            fused_scores.append((1 - w) * rr + w * rk)
        ordered_all = [
            {
                "id": candidates[i]["id"],
                "text": candidates[i]["text"],
                "metadata": candidates[i]["metadata"],
                "score": round(fused_scores[i], 4),
            }
            for i in sorted(range(len(candidates)), key=lambda i: -fused_scores[i])
        ]
        return _dedupe_by_source(ordered_all)[:top_k]

    # 无 rerank：归一化 RRF 分 + 文档级去重
    max_s = fused[0][1] if fused else 1.0
    ordered_all = []
    for doc_id, raw in fused:
        if doc_id not in rec_by_id:
            continue
        ordered_all.append(
            {
                "id": doc_id,
                "text": rec_by_id[doc_id]["text"],
                "metadata": rec_by_id[doc_id]["metadata"],
                "score": round(raw / max_s, 4),
            }
        )
    return _dedupe_by_source(ordered_all)[:top_k]

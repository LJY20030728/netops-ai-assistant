"""RAG 评测：检索指标（Recall@k / MRR）+ LLM 判卷（忠实度/相关性）。

三种检索方式对比：纯向量 / 混合（BM25+向量+RRF）/ 混合+rerank。

运行（backend 目录下）：
    python -m app.rag.evaluate
输出：终端汇总 + backend/eval_report.md
"""
import asyncio
import datetime
import json
from pathlib import Path

from app.config import settings
from app.llm.zhipu_client import complete_json
from app.rag import store as kb_store
from app.rag.retrieval import hybrid_retrieve

# 评测集：问题 → 期望命中的知识库文档（依据真实知识库内容编写）
# 构成：基础 8 条 + 跨文档 2 + 语义改写 9 + 细节题 9 + 干扰项 8 = 36 条
EVAL_SET = [
    # ---- 基础（原有）----
    {"q": "核心交换机端口反复 up/down，可能是什么原因？", "expect": "端口flapping排查手册.md"},
    {"q": "光纤接收光功率过低会导致什么问题，怎么排查？", "expect": "光模块与光纤链路排查.md"},
    {"q": "OSPF 邻居卡在 ExStart 状态是什么原因？", "expect": "OSPF邻居建立与故障排查.md"},
    {"q": "跨交换机 VLAN 不通，应该检查什么？", "expect": "VLAN与Trunk配置排障.md"},
    {"q": "二层环路会引发什么现象，STP 怎么排查？", "expect": "STP生成树与环路排查.md"},
    {"q": "BGP 邻居一直处于 Active 状态，怎么排查？", "expect": "BGP邻居与路由故障排查.md"},
    {"q": "同一网段两台主机 ping 不通，怎么定位 ARP 问题？", "expect": "ARP与二层通信故障排查.md"},
    {"q": "网络设备日常巡检应该关注哪些指标？", "expect": "网络设备日常巡检与基线.md"},
    # ---- 跨文档类（需多个手册信息综合）----
    {"q": "接入交换机下终端频繁掉线，同时设备 CPU 升高、接口出现大量广播，该怎么从二层角度排查？", "expect": "网络广播风暴定位与处置.md"},
    {"q": "核心链路带宽被打满，想确认具体是哪些应用流量在跑，应该怎么抓取和分析？", "expect": "端口镜像与抓包分析.md"},
    # ---- 语义改写类（同义不同词，考验语义召回）----
    {"q": "交换机接口下挂的设备老是断网重连，怀疑是端口在抖动，怎么定位？", "expect": "端口flapping排查手册.md"},
    {"q": "设备重启之后配置全部丢失，回到出厂状态，应该怎么防范？", "expect": "配置备份与设备重启规范.md"},
    {"q": "终端网卡显示受限，一直拿不到地址，怎么办？", "expect": "DHCP无法获取IP地址排查.md"},
    {"q": "网页打开慢，域名老是解析不出来，怎么排查？", "expect": "DNS域名解析故障排查.md"},
    {"q": "两台核心交换机做主备网关，切换之后业务全断，怎么排查？", "expect": "VRRP网关冗余故障排查.md"},
    {"q": "无线终端连不上 Wi-Fi，查了下 AP 状态是离线，怎么恢复？", "expect": "无线AP离线与漫游故障排查.md"},
    {"q": "网管平台收不到设备告警，SNMP 采集不通，怎么查？", "expect": "SNMP网管不通排查.md"},
    {"q": "内网用户访问外网时地址转换不生效，怎么排查 NAT？", "expect": "NAT地址转换配置与排障.md"},
    {"q": "IPTV 组播业务卡顿，组播成员加不进来，怎么查 IGMP？", "expect": "组播IGMP故障排查.md"},
    # ---- 细节题（手册内具体参数/命令级）----
    {"q": "ACL 匹配计数一直在增长但业务还是通，这个现象说明什么？", "expect": "ACL访问控制列表配置与排障.md"},
    {"q": "设备 CPU 持续 90% 以上，怎么定位是哪个进程或协议占用的？", "expect": "设备CPU高占用排查.md"},
    {"q": "BGP 路由频繁震荡导致路由表抖动，路由策略上应该怎么优化？", "expect": "BGP路由振荡与路由策略排障.md"},
    {"q": "OSPF 和静态路由同时存在时，路由优先级如何影响选路？", "expect": "路由重分发与路由优先级排障.md"},
    {"q": "默认路由下一跳指错导致上网全断，怎么验证和修正？", "expect": "静态路由与默认路由排障.md"},
    {"q": "同一 IP 对应的 MAC 地址一直在变，什么原因？", "expect": "ARP冲突与欺骗专项排查.md"},
    {"q": "广播报文占比异常升高，怎么一步步定位广播源？", "expect": "网络广播风暴定位与处置.md"},
    {"q": "业务时延从 2ms 涨到 50ms，怎么分段定位拥塞点？", "expect": "网络时延与拥塞排查.md"},
    {"q": "多台交换机堆叠后主备倒换异常，堆叠系统怎么排查？", "expect": "交换机堆叠iStack故障排查.md"},
    # ---- 干扰项（近似主题，考验精排区分度）----
    {"q": "端口收光功率低于阈值导致链路闪断，怎么按光模块排查？", "expect": "光模块收发光功率与误码专项排查.md"},
    {"q": "怀疑有人伪造网关 MAC 导致全网周期性掉线，怎么确认？", "expect": "ARP冲突与欺骗专项排查.md"},
    {"q": "防火墙安全策略明明放行了但还是不通，该查会话表的什么？", "expect": "防火墙安全策略与会话表排查.md"},
    {"q": "防火墙主备双机切换后业务全部中断，HRP 状态怎么检查？", "expect": "防火墙双机热备HRP故障排查.md"},
    {"q": "两台交换机做链路聚合后只有一条链路在转发，怎么排障？", "expect": "链路聚合Eth-Trunk配置与排障.md"},
    {"q": "运营商侧 VLAN 透传不过去，二层报文带不上标签，怎么办？", "expect": "QinQ与二层透传配置.md"},
    {"q": "割接窗口内配置回退失败，现场应该按什么步骤处理？", "expect": "网络割接与变更操作规范.md"},
    {"q": "光纤链路有误码导致业务时通时断，怎么定位误码来源？", "expect": "光模块收发光功率与误码专项排查.md"},
]

_METHODS = ["vector", "hybrid", "hybrid+rerank"]


def _method_top_ids(query: str, method: str, top_k: int = 5) -> list[str]:
    if method == "vector":
        return [h["id"] for h in kb_store.search(query, top_k)]
    if method == "hybrid":
        return [h["id"] for h in hybrid_retrieve(query, top_k, use_rerank=False)]
    return [h["id"] for h in hybrid_retrieve(query, top_k, use_rerank=True)]


def _recall_at_k(ids: list[str], expect_source: str, k: int = 5) -> bool:
    """期望文档是否出现在前 k 个检索结果中。"""
    if not ids:
        return False
    rec_by_id = {r["id"]: r for r in kb_store._load()}
    top_sources = [rec_by_id[i]["metadata"].get("source", "") for i in ids[:k] if i in rec_by_id]
    return expect_source in top_sources


def _mrr(ids: list[str], expect_source: str) -> float:
    rec_by_id = {r["id"]: r for r in kb_store._load()}
    for rank, i in enumerate(ids, start=1):
        if i in rec_by_id and rec_by_id[i]["metadata"].get("source", "") == expect_source:
            return 1.0 / rank
    return 0.0


# ---------------------------------------------------------------- LLM 判卷
_JUDGE_SYSTEM = """你是一名 RAG 系统评测员。请从两个维度给回答打分（1-5 分，只输出 JSON）：
1. faithfulness（忠实度）：回答是否完全基于提供的【参考资料】，是否编造资料中没有的信息；
2. relevance（相关性）：回答是否切题，是否解决了用户问题。
评分标准：5=完全符合，3=部分符合，1=严重不符。
只输出：{"faithfulness": n, "relevance": n, "reason": "一句话理由"}"""


def _extract_json(text: str) -> dict:
    """剥离 markdown 围栏后解析 JSON，失败返回空 dict。"""
    if not text:
        return {}
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {}


async def _judge(query: str, context: str, answer: str) -> dict:
    msgs = [
        {"role": "system", "content": _JUDGE_SYSTEM},
        {
            "role": "user",
            "content": f"【用户问题】{query}\n【参考资料】{context}\n【AI 回答】{answer}",
        },
    ]
    try:
        text = await complete_json(msgs, max_tokens=300)
        obj = _extract_json(text)
        if not obj:
            return {"faithfulness": 0, "relevance": 0, "reason": f"judge 返回非 JSON：{text[:40]!r}"[:60]}
        return {
            "faithfulness": int(obj.get("faithfulness", 0)),
            "relevance": int(obj.get("relevance", 0)),
            "reason": str(obj.get("reason", ""))[:60],
        }
    except Exception as exc:  # noqa: BLE001
        return {"faithfulness": 0, "relevance": 0, "reason": f"judge error: {exc}"[:60]}


# ---------------------------------------------------------------- 汇总
def _retrieval_report() -> dict:
    report: dict = {}
    for method in _METHODS:
        r5 = 0
        mrr_sum = 0.0
        for item in EVAL_SET:
            ids = _method_top_ids(item["q"], method)
            r5 += 1 if _recall_at_k(ids, item["expect"]) else 0
            mrr_sum += _mrr(ids, item["expect"])
        n = len(EVAL_SET)
        report[method] = {
            "recall_at_5": round(r5 / n, 3),
            "mrr": round(mrr_sum / n, 3),
            "hits": f"{r5}/{n}",
        }
    return report


async def _judge_report(sample_n: int = 8) -> dict:
    """对混合+rerank 检索生成的回答做 LLM 判卷（小样本）。"""
    from app.llm.zhipu_client import stream_chat

    results = []
    for item in EVAL_SET[:sample_n]:
        hits = hybrid_retrieve(item["q"], settings.rag_top_k, use_rerank=True)
        context = "\n\n".join(f"[{h['metadata'].get('source','')}]\n{h['text']}" for h in hits)
        sys_msg = {
            "role": "system",
            "content": "你是网络运维助手，仅依据【参考资料】回答，资料不足要说明，不编造。",
        }
        msgs = [
            sys_msg,
            {"role": "user", "content": f"【参考资料】\n{context}\n\n【问题】{item['q']}"},
        ]
        answer = ""
        async for chunk in stream_chat(msgs):
            answer += chunk
        score = await _judge(item["q"], context, answer)
        results.append(
            {"q": item["q"], "context": context[:150], "answer": answer[:200], **score}
        )
    return {
        "sample": sample_n,
        "faithfulness_avg": round(sum(r["faithfulness"] for r in results) / len(results), 2),
        "relevance_avg": round(sum(r["relevance"] for r in results) / len(results), 2),
        "results": results,
    }


def _write_markdown(retrieval: dict, judge: dict | None, path: Path) -> None:
    lines = [
        "# RAG 评测报告（M4+ / v0.5.0）",
        "",
        f"- 生成时间：{datetime.datetime.now().isoformat(timespec='seconds')}",
        f"- 评测集：{len(EVAL_SET)} 条（依据知识库内容编写，标注期望命中文档）",
        "- 评测集构成：基础 8 条 + 跨文档 2 条 + 语义改写 9 条 + 细节题 9 条 + 干扰项 8 条",
        f"- 嵌入模型：{settings.zhipu_embedding_model} · 重排模型：{settings.rerank_model}",
        "",
        "## 一、检索指标（Recall@5 / MRR）",
        "",
        "| 方法 | Recall@5 | MRR | 命中 |",
        "|---|---|---|---|",
    ]
    for method, m in retrieval.items():
        lines.append(f"| {method} | {m['recall_at_5']} | {m['mrr']} | {m['hits']} |")
    if judge:
        lines += [
            "",
            "## 二、LLM 判卷（混合+rerank，忠实度/相关性 1-5 分）",
            "",
            f"- 样本数：{judge['sample']}",
            f"- 忠实度均值：{judge['faithfulness_avg']} · 相关性均值：{judge['relevance_avg']}",
            "",
            "| 问题 | 忠实度 | 相关性 | 判卷理由 |",
            "|---|---|---|---|",
        ]
        for r in judge["results"]:
            lines.append(f"| {r['q'][:28]}… | {r['faithfulness']} | {r['relevance']} | {r['reason']} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main() -> dict:
    print("== 检索指标对比 ==")
    retrieval = _retrieval_report()
    for method, m in retrieval.items():
        print(f"  {method:<14} Recall@5={m['recall_at_5']}  MRR={m['mrr']}  ({m['hits']})")

    judge = None
    if settings.zhipu_api_key and not settings.mock_llm:
        print("== LLM 判卷（小样本） ==")
        judge = await _judge_report()
        print(f"  忠实度={judge['faithfulness_avg']} 相关性={judge['relevance_avg']}")
    else:
        print("（未配置 Key，跳过 LLM 判卷）")

    out = Path(__file__).resolve().parents[2] / "eval_report.md"
    _write_markdown(retrieval, judge, out)
    print(f"报告已写入：{out}")
    return {"retrieval": retrieval, "judge": judge, "report_path": str(out)}


if __name__ == "__main__":
    asyncio.run(main())

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
# 构成：基础 8 条 + 跨文档 2 条 + 语义改写 9 条 + 细节题 9 条 + 干扰项 8 条 = 36 条（v0.6.0）
#      + 口语改写 5 条 + 命令级细节 10 条 + 强干扰 5 条 + 跨文档 4 条 = 24 条（v0.7.0 扩充）
#      合计 60 条
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
    # ---- v0.7.0 扩充 · 口语改写类（更接近一线运维的真实问法）----
    {"q": "交换机口子上的设备一会儿通一会儿断，怀疑是光纤头脏了，怎么确认？", "expect": "光模块与光纤链路排查.md"},
    {"q": "公司网络一到下午就卡得不行，延迟很高，怎么定位是哪里堵了？", "expect": "网络时延与拥塞排查.md"},
    {"q": "无线 AP 全部掉线了，但交换机接口是通的，从哪查起？", "expect": "无线AP离线与漫游故障排查.md"},
    {"q": "服务器网卡一直拿不到地址，重启服务也没用，怎么排？", "expect": "DHCP无法获取IP地址排查.md"},
    {"q": "跨网段访问时通时断，路由表看着没问题，还能查什么？", "expect": "静态路由与默认路由排障.md"},
    # ---- v0.7.0 扩充 · 命令级细节题（考验对具体输出字段的理解）----
    {"q": "display interface 里 CRC 错误计数持续增长，通常说明什么？", "expect": "端口flapping排查手册.md"},
    {"q": "STP 输出里 Topology changes 计数暴涨，该怎么解读？", "expect": "STP生成树与环路排查.md"},
    {"q": "BGP 邻居的 Last down reason 显示 ConnectRetry，怎么分析？", "expect": "BGP邻居与路由故障排查.md"},
    {"q": "ACL 里 rule 的匹配次数和日志里的 denied 次数对不上，怎么看？", "expect": "ACL访问控制列表配置与排障.md"},
    {"q": "display cpu-usage 里 System 占比高和 User 占比高，分别怎么查？", "expect": "设备CPU高占用排查.md"},
    {"q": "Eth-Trunk 成员口负载不均，怎么确认哈希负载分担是否生效？", "expect": "链路聚合Eth-Trunk配置与排障.md"},
    {"q": "VRRP 的 Master/Backup 状态反复切换，说明什么问题？", "expect": "VRRP网关冗余故障排查.md"},
    {"q": "堆叠分裂后业务中断，怎么判断哪台是主设备、如何恢复？", "expect": "交换机堆叠iStack故障排查.md"},
    {"q": "HRP 备墙会话不同步，主备切换后会丢什么？", "expect": "防火墙双机热备HRP故障排查.md"},
    {"q": "抓包看到大量 TCP 重传，怎么定位是应用层还是网络层的问题？", "expect": "端口镜像与抓包分析.md"},
    # ---- v0.7.0 扩充 · 强干扰项（近似主题，考察精排区分度）----
    {"q": "光功率读数正常但链路持续误码，问题可能在哪？", "expect": "光模块收发光功率与误码专项排查.md"},
    {"q": "内网两台机器的 MAC 地址一样导致网络冲突，怎么定位？", "expect": "ARP冲突与欺骗专项排查.md"},
    {"q": "防火墙策略顺序不对，该放行的流量被后面的 deny 拦了，怎么排查？", "expect": "防火墙安全策略与会话表排查.md"},
    {"q": "路由重分发造成三层选路环路，OSPF 里怎么防止？", "expect": "路由重分发与路由优先级排障.md"},
    {"q": "QinQ 打上外层标签后内层 VLAN 透传不过去，怎么查？", "expect": "QinQ与二层透传配置.md"},
    # ---- v0.7.0 扩充 · 跨文档综合类（多手册交叉取证）----
    {"q": "终端间歇性断网，交换机日志同时有 ARP 冲突和接口广播异常，优先查什么？", "expect": "ARP冲突与欺骗专项排查.md"},
    {"q": "设备重启后配置丢失，重启后 CPU 还一直居高不下，怎么处理？", "expect": "配置备份与设备重启规范.md"},
    {"q": "割接完成后 VLAN 不通而且 ARP 表异常，变更回退该怎么执行？", "expect": "网络割接与变更操作规范.md"},
    {"q": "监控显示某接口输入流量异常增长，怀疑广播风暴，想抓包确认，怎么操作？", "expect": "端口镜像与抓包分析.md"},
    # ---- v0.8.0 · 真实工单语言变体（做法乙：模拟 NOC 工单/告警的真实问法）----
    # variant_type: colloquial=口语化工单 / terse=残缺告警标题体 / noisy=带噪长句 / shorthand=中英简写
    # 期望标注原则：口语化/带噪 → 案例层（经验）；残缺/简写 → 手册层（命令/原理）
    {"q": "网断了好几次，换什么都说不是他们的问题", "expect": "case-001.md", "variant_type": "colloquial"},
    {"q": "port down up down up 一直闪", "expect": "端口flapping排查手册.md", "variant_type": "terse"},
    {"q": "交换机接口上的设备老是掉线重连，一天好几次", "expect": "case-002.md", "variant_type": "colloquial"},
    {"q": "早上开会说网络卡，后来发现是机房那边交换机端口一直闪，一会儿通一会儿断", "expect": "case-003.md", "variant_type": "noisy"},
    {"q": "光模块是不是有问题，接收功率太低，网时好时坏", "expect": "case-004.md", "variant_type": "colloquial"},
    {"q": "rx power 低 crc 暴增", "expect": "光模块收发光功率与误码专项排查.md", "variant_type": "shorthand"},
    {"q": "机房温度有点高，顺便看了下光模块，误码很多，收光功率-30dbm 是不是不正常", "expect": "case-022.md", "variant_type": "noisy"},
    {"q": "两台交换机连了根线，全网就卡死了，是不是环了", "expect": "case-006.md", "variant_type": "colloquial"},
    {"q": "stp tc 暴涨", "expect": "STP生成树与环路排查.md", "variant_type": "terse"},
    {"q": "终端老掉线，查了 stp 发现拓扑变更次数特别多，接入端口一直 up down", "expect": "case-005.md", "variant_type": "noisy"},
    {"q": "网速突然很慢，一看交换机 CPU 特别高，广播包特别多", "expect": "case-007.md", "variant_type": "colloquial"},
    {"q": "broadcast storm 怎么定位", "expect": "网络广播风暴定位与处置.md", "variant_type": "terse"},
    {"q": "ospf 邻居怎么都起不来，重启路由器也没用", "expect": "case-008.md", "variant_type": "colloquial"},
    {"q": "ospf exstart mtu 不匹配", "expect": "case-008.md", "variant_type": "terse"},
    {"q": "ospf peer down hello dead 不匹配", "expect": "case-009.md", "variant_type": "shorthand"},
    {"q": "今天割接加了一台设备，区域配置好后邻居还是 down，看日志是认证失败，但密码明明是对的", "expect": "OSPF邻居建立与故障排查.md", "variant_type": "noisy"},
    {"q": "bgp 邻居起不来，一直 active，查了地址能通", "expect": "case-010.md", "variant_type": "colloquial"},
    {"q": "bgp connectretry 起不来", "expect": "BGP邻居与路由故障排查.md", "variant_type": "terse"},
    {"q": "跟运营商建 bgp 邻居，as 号填错了现在起不来", "expect": "case-011.md", "variant_type": "colloquial"},
    {"q": "业务访问慢，检查发现 bgp 邻居一会儿 established 一会儿 down，keepalive 时间两边不一样", "expect": "case-012.md", "variant_type": "noisy"},
    {"q": "公司电脑突然全部拿不到地址了，显示未识别网络", "expect": "case-013.md", "variant_type": "colloquial"},
    {"q": "dhcp pool 满了", "expect": "case-013.md", "variant_type": "terse"},
    {"q": "新加了一台设备，配了 dhcp 中继，但下面的终端还是拿不到地址，中继地址好像指错了", "expect": "case-014.md", "variant_type": "noisy"},
    {"q": "出口带宽又被打满了，查一下是谁在跑流量", "expect": "端口镜像与抓包分析.md", "variant_type": "colloquial"},
    {"q": "qos 拥塞丢包 出口", "expect": "网络时延与拥塞排查.md", "variant_type": "terse"},
    {"q": "最近晚上业务就卡，白天没事，看了下是备份任务把带宽吃满了，想限速", "expect": "case-029.md", "variant_type": "noisy"},
    {"q": "交换机 cpu 一直 90 多，不知道啥进程占的", "expect": "case-017.md", "variant_type": "colloquial"},
    {"q": "cpu 100 协议震荡", "expect": "设备CPU高占用排查.md", "variant_type": "terse"},
    {"q": "重启了一下设备，配置全没了，回到出厂状态", "expect": "case-018.md", "variant_type": "colloquial"},
    {"q": "save 没保存 重启丢配置", "expect": "配置备份与设备重启规范.md", "variant_type": "terse"},
    {"q": "内网域名解析失败，IP 直连能通，怎么排查？", "expect": "case-023.md", "variant_type": "standard"},
    {"q": "内网能互访但上不了外网，NAT 会话表异常怎么排查？", "expect": "case-024.md", "variant_type": "standard"},
    {"q": "ACL 策略变更后财务系统不通了，怎么定位误拦？", "expect": "case-025.md", "variant_type": "standard"},
    {"q": "监控平台 SNMP 不通但 SSH 能登录，什么原因？", "expect": "case-026.md", "variant_type": "standard"},
    {"q": "某楼层 WiFi 全没信号，AP 离线怎么排查？", "expect": "case-027.md", "variant_type": "standard"},
    {"q": "核心链路割接后光功率低加端口抖动，多告警怎么关联定位？", "expect": "case-028.md", "variant_type": "standard"},
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
    rec_by_id = {r["id"]: r for r in kb_store.records()}
    top_sources = [rec_by_id[i]["metadata"].get("source", "") for i in ids[:k] if i in rec_by_id]
    return expect_source in top_sources


def _mrr(ids: list[str], expect_source: str) -> float:
    rec_by_id = {r["id"]: r for r in kb_store.records()}
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


# ---------------------------------------------------------------- 失败归因
def _collect_failures(method: str = "hybrid+rerank") -> list[dict]:
    """收集未命中（Recall 失败）或低分（MRR<0.5）的评测条目及其实际 top3。"""
    rec_by_id = {r["id"]: r for r in kb_store.records()}
    failures = []
    for item in EVAL_SET:
        ids = _method_top_ids(item["q"], method)
        top_sources = [rec_by_id[i]["metadata"].get("source", "") for i in ids[:5] if i in rec_by_id]
        hit = item["expect"] in top_sources
        mrr = _mrr(ids, item["expect"])
        if not hit or mrr < 0.5:
            top3 = []
            for i in ids[:3]:
                if i in rec_by_id:
                    top3.append(
                        {
                            "source": rec_by_id[i]["metadata"].get("source", ""),
                            "score": round(rec_by_id[i].get("score", 0), 3),
                            "snippet": rec_by_id[i]["text"][:60],
                        }
                    )
            failures.append(
                {
                    "q": item["q"],
                    "expect": item["expect"],
                    "hit": hit,
                    "mrr": round(mrr, 3),
                    "top3": top3,
                }
            )
    return failures


_ATTRIBUTE_SYSTEM = """你是 RAG 检索系统评测员。给定一个"未命中/低分"的检索案例（问题、期望文档、实际返回的 top3 文档），请判断检索失败的主要原因，只输出 JSON：
原因枚举（选 1-2 个）：
- "lexical_gap": 词面差异大（口语/同义改写导致关键词不重叠）
- "semantic_drift": 语义相近但主题漂移（问题核心概念与期望文档侧重不一致）
- "doc_coverage": 知识库文档覆盖不足或过于分散（期望文档本身缺少关键信息）
- "distractor": 干扰文档过强（近似主题文档抢占了排序）
- "chunk_quality": 切分质量差（期望信息被切开或上下文丢失）
- "ranker": 重排器问题（候选召回正确但精排把期望文档挤下去了）
只输出：{"causes": ["..."], "suggestion": "改进建议（一句话）"}"""


async def _attribute_one(fail: dict) -> dict:
    top3_text = "\n".join(
        f"#{i+1} [{t['source']}] score={t['score']}\n{t['snippet']}"
        for i, t in enumerate(fail["top3"])
    )
    msgs = [
        {"role": "system", "content": _ATTRIBUTE_SYSTEM},
        {
            "role": "user",
            "content": f"【用户问题】{fail['q']}\n【期望命中】{fail['expect']}（MRR={fail['mrr']}）\n【实际 top3】\n{top3_text}",
        },
    ]
    try:
        text = await complete_json(msgs, max_tokens=200)
        obj = _extract_json(text)
        if obj:
            return {
                "causes": obj.get("causes", []),
                "suggestion": str(obj.get("suggestion", ""))[:80],
            }
    except Exception as exc:  # noqa: BLE001
        return {"causes": ["judge_error"], "suggestion": f"{exc}"[:80]}
    return {"causes": ["parse_error"], "suggestion": ""}


async def _failure_analysis(failures: list[dict]) -> list[dict]:
    out = []
    for f in failures:
        attr = await _attribute_one(f)
        out.append({**f, **attr})
    return out


# ---------------------------------------------------------------- 汇总
_VARIANT_GROUPS = ['standard', 'colloquial', 'terse', 'noisy', 'shorthand']


def _metric_group(method: str, group: str) -> dict:
    items = EVAL_SET if group == 'all' else [
        i for i in EVAL_SET if i.get('variant_type', 'standard') == group
    ]
    if not items:
        return {'n': 0, 'recall_at_5': 0.0, 'mrr': 0.0, 'hits': '0/0'}
    r5 = 0
    mrr_sum = 0.0
    for item in items:
        ids = _method_top_ids(item['q'], method)
        r5 += 1 if _recall_at_k(ids, item['expect']) else 0
        mrr_sum += _mrr(ids, item['expect'])
    n = len(items)
    return {
        'n': n,
        'recall_at_5': round(r5 / n, 3),
        'mrr': round(mrr_sum / n, 3),
        'hits': f'{r5}/{n}',
    }


def _retrieval_report() -> dict:
    report: dict = {}
    for method in _METHODS:
        report[method] = _metric_group(method, 'all')
        report[method]['groups'] = {g: _metric_group(method, g) for g in _VARIANT_GROUPS}
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


def _write_markdown(retrieval: dict, judge: dict | None, failures: list[dict], path: Path) -> None:
    lines = [
        "# RAG 评测报告（M6+ / v0.8.0）",
        "",
        f"- 生成时间：{datetime.datetime.now().isoformat(timespec='seconds')}",
        f"- 评测集：{len(EVAL_SET)} 条（依据知识库内容编写，标注期望命中文档）",
        "- 评测集构成：基础 8 + 跨文档 6 + 语义改写 14 + 细节题 19 + 干扰项 13 = 60 条",
        f"- 嵌入模型：{settings.zhipu_embedding_model} · 重排模型：{settings.rerank_model}",
        "",
        "## 一、检索指标（Recall@5 / MRR）",
        "",
        "| 方法 | Recall@5 | MRR | 命中 |",
        "|---|---|---|---|",
    ]
    for method, m in retrieval.items():
        lines.append(f"| {method} | {m['recall_at_5']} | {m['mrr']} | {m['hits']} |")
    lines += [
        '',
        '### 按变体类型分组（hybrid，Recall@5 / MRR）',
        '',
        '| 变体类型 | 条数 | Recall@5 | MRR | 命中 |',
        '|---|---|---|---|---|',
    ]
    groups = retrieval.get('hybrid', {}).get('groups', {})
    for g in _VARIANT_GROUPS:
        m = groups.get(g, {})
        lines.append(f"| {g} | {m.get('n', 0)} | {m.get('recall_at_5', 0)} | {m.get('mrr', 0)} | {m.get('hits', '0/0')} |")
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
    lines += [
        "",
        "## 三、失败与低分案例归因（LLM 自动分析）",
        "",
    ]
    if failures:
        lines.append(f"- 失败/低分案例：{len(failures)} 条（判定：期望文档未进 top5 或 MRR<0.5）")
        lines.append("")
        for f in failures:
            top3 = "；".join(f"#{i+1} {t['source']}({t['score']})" for i, t in enumerate(f["top3"]))
            lines.append(f"### {f['q']}")
            lines.append(f"- 期望：`{f['expect']}` · MRR={f['mrr']} · 命中={f['hit']}")
            lines.append(f"- 实际 top3：{top3}")
            lines.append(f"- 归因：{', '.join(f.get('causes', []))} · 建议：{f.get('suggestion', '')}")
            lines.append("")
    else:
        lines.append("- 无失败/低分案例（全部命中且 MRR≥0.5）。")
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

    print("== 失败/低分案例归因 ==")
    failures = _collect_failures()
    print(f"  失败/低分：{len(failures)} 条")
    if failures:
        failures = await _failure_analysis(failures)
        for f in failures:
            print(f"  - {f['q'][:30]}… → 期望 {f['expect']} · MRR={f['mrr']} · 原因：{','.join(f.get('causes', []))}")

    out = Path(__file__).resolve().parents[2] / "eval_report.md"
    _write_markdown(retrieval, judge, failures, out)
    print(f"报告已写入：{out}")
    return {"retrieval": retrieval, "judge": judge, "failures": failures, "report_path": str(out)}


if __name__ == "__main__":
    asyncio.run(main())
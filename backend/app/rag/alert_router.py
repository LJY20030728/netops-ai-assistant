"""L3 告警路由：把用户输入映射到结构化告警类型，确定性路由到手册/案例。

设计（v0.8.0 双通道检索的"通道 A"）：
- alert_map.json 是结构化规则表（告警类型 → 可能根因 → 指向手册/案例），不走 RAG；
- route_alert(query)：关键词子串匹配，多命中取优先级最高、匹配数最多者；
- 命中结果用于：① retrieval 前置加权（通道 A）；② Agent prompt 注入结构化起点。
"""
import json
import threading
from pathlib import Path

from app.config import KB_DIR

ALERT_MAP_FILE: Path = KB_DIR / "alert_map.json"

_PRIORITY_RANK = {"P1": 0, "P2": 1, "P3": 2}

_lock = threading.Lock()
_cache: dict | None = None


def _load_alert_map() -> dict:
    global _cache
    if _cache is None:
        with _lock:
            if _cache is None:
                _cache = json.loads(ALERT_MAP_FILE.read_text(encoding="utf-8"))
    return _cache


def reset_cache() -> None:
    """测试/热更新用：清空缓存强制重读。"""
    global _cache
    with _lock:
        _cache = None


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def route_alert(query: str) -> dict | None:
    """把查询/工单文本路由到最相关的告警。

    返回结构：{alarm_type, name, possible_causes, manuals, cases,
               suggested_cmds, priority, matched_keywords}
    无命中返回 None。
    """
    q = _norm(query)
    if not q:
        return None
    data = _load_alert_map()
    hits: list[dict] = []
    for alert in data.get("alerts", []):
        matched = [k for k in alert.get("keywords", []) if _norm(k) and _norm(k) in q]
        if matched:
            hits.append(
                {
                    **alert,
                    "matched_keywords": matched,
                    "_rank": (_PRIORITY_RANK.get(alert.get("priority", "P3"), 2), -len(matched)),
                }
            )
    if not hits:
        return None
    hits.sort(key=lambda h: h.pop("_rank"))
    return hits[0]


def list_alarm_types() -> list[str]:
    """全部告警类型（供文档/校验）。"""
    return [a["alarm_type"] for a in _load_alert_map().get("alerts", [])]


if __name__ == "__main__":  # pragma: no cover
    print(f"alert_map.json 共 {len(list_alarm_types())} 种告警：")
    for t in list_alarm_types():
        print("  -", t)

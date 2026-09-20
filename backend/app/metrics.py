"""轻量请求级 metrics：每次 chat 请求写一行 JSONL。

落盘：backend/data/metrics.jsonl
字段：ts, path, latency_ms, rag_ms, llm_ms, prompt_tokens, completion_tokens, steps, ok, error
聚合：summary(n) 返回最近 n 条的 P50/P95 延迟、总 token、错误率。
"""
import json
import threading
import time
from pathlib import Path

from app.config import DATA_DIR

_METRICS_FILE = DATA_DIR / "metrics.jsonl"
_lock = threading.Lock()


def record(**fields) -> None:
    """记录一次请求指标。写失败静默（metrics 不能影响主流程）。"""
    fields["ts"] = round(time.time(), 3)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with _lock:
            with _METRICS_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(fields, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return round(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo), 1)


def summary(n: int = 100) -> dict:
    """返回最近 n 条请求的聚合指标。"""
    if not _METRICS_FILE.exists():
        return {"count": 0, "note": "暂无 metrics"}
    try:
        lines = _METRICS_FILE.read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return {"count": 0, "note": "读取失败"}
    recs = []
    for ln in lines:
        try:
            recs.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    if not recs:
        return {"count": 0}
    lats = sorted(r.get("latency_ms", 0) for r in recs)
    rag = sorted(r.get("rag_ms", 0) for r in recs if r.get("rag_ms"))
    llm = sorted(r.get("llm_ms", 0) for r in recs if r.get("llm_ms"))
    total_prompt = sum(r.get("prompt_tokens", 0) for r in recs)
    total_completion = sum(r.get("completion_tokens", 0) for r in recs)
    errors = sum(1 for r in recs if not r.get("ok", True))
    return {
        "count": len(recs),
        "latency_p50_ms": _percentile(lats, 0.5),
        "latency_p95_ms": _percentile(lats, 0.95),
        "rag_p50_ms": _percentile(rag, 0.5) if rag else 0,
        "llm_p50_ms": _percentile(llm, 0.5) if llm else 0,
        "prompt_tokens_total": total_prompt,
        "completion_tokens_total": total_completion,
        "error_rate": round(errors / len(recs), 3),
        "last": recs[-1] if recs else None,
    }

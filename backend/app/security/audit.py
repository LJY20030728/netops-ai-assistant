"""审计日志：以 JSON Lines 追加写入 backend/data/audit.jsonl。

记录动作、执行者（角色）、时间与关键细节，供安全审计与排查追溯。
data/ 已被 .gitignore 忽略，日志不提交。
"""
import json
import threading
import time
from datetime import datetime, timezone, timedelta

from app.config import DATA_DIR, settings

_lock = threading.Lock()
_AUDIT_FILE = DATA_DIR / "audit.jsonl"

_CST = timezone(timedelta(hours=8))


def log(event: str, actor: str = "anonymous", action: str = "", detail: str = "") -> None:
    if not settings.audit_enabled:
        return
    record = {
        "ts": datetime.now(_CST).isoformat(timespec="seconds"),
        "event": event,
        "actor": actor,
        "action": action,
        "detail": detail[:2000],
    }
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with _lock:
            with _AUDIT_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # 审计失败不应阻断主流程


def count() -> int:
    if not _AUDIT_FILE.exists():
        return 0
    return sum(1 for _ in _AUDIT_FILE.open(encoding="utf-8"))

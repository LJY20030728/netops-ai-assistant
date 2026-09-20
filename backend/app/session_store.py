"""会话持久化：多轮对话落盘（JSONL），刷新/重启后可恢复。

存储位置：backend/data/sessions/<session_id>.jsonl
每行一条消息：{"role": "user"|"assistant", "content": "...", "ts": 时间戳}
"""
import json
import time
from pathlib import Path

from app.config import DATA_DIR

SESSION_DIR = DATA_DIR / "sessions"


# 会话 ID 白名单之外一律拒绝：路径分隔符 + Windows 非法文件名字符 + 控制字符
_ILLEGAL_CHARS = set('<>:"/\\|?*') | set(chr(i) for i in range(32))


def _path(session_id: str) -> Path:
    # 会话 ID 只允许安全字符，防路径穿越与非法文件名（Windows 上 | * ? < > 会导致 OSError）
    if not session_id or ".." in session_id or any(ch in session_id for ch in _ILLEGAL_CHARS):
        raise ValueError("非法 session_id")
    return SESSION_DIR / f"{session_id}.jsonl"


def load(session_id: str) -> list[dict]:
    p = _path(session_id)
    if not p.exists():
        return []
    msgs = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msgs.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return msgs


def append(session_id: str, role: str, content: str) -> None:
    if not content:
        return
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    p = _path(session_id)
    with p.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"role": role, "content": content, "ts": time.strftime("%Y-%m-%d %H:%M:%S")},
                ensure_ascii=False,
            )
            + "\n"
        )


def list_sessions(limit: int = 20) -> list[dict]:
    """列出最近会话（按修改时间倒序），供前端侧栏。

    title 取该会话第一条 user 消息的前 14 字（类似豆包会话标题）。
    """
    if not SESSION_DIR.exists():
        return []
    out = []
    for p in sorted(SESSION_DIR.glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
        title = p.stem[-8:]
        for ln in lines:
            try:
                m = json.loads(ln)
                if m.get("role") == "user":
                    # 取最新一条 user 消息作为标题（随对话实时更新）
                    title = (m.get("content") or "").strip().replace("\n", " ")[:14]
            except json.JSONDecodeError:
                continue
        out.append(
            {
                "session_id": p.stem,
                "title": title or p.stem[-8:],
                "messages": len(lines),
                "updated": p.stat().st_mtime,
            }
        )
    return out

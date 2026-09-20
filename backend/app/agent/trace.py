"""Agent trace 落盘：每次 agent 跑的每一步都写成 JSONL，用于可观测性与复盘。

目录：backend/data/traces/<session_id>/
  - steps.jsonl   每一行一步：thought / tool_call / tool_result / finish / error
  - summary.json  本次运行汇总：步数、工具调用数、总耗时、错误

设计原则：
- 不依赖 LLM、不阻塞主流程；写文件失败不影响 agent 运行（try/except 吞掉）
- session_id 为空时用时间戳兜底，保证每次都有迹可循
- 不存敏感凭证（设备密码本来就不在 agent 层）
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from app.config import DATA_DIR


class AgentTrace:
    def __init__(self, session_id: str | None = None):
        safe = (session_id or "").strip() or f"anon-{int(time.time())}"
        # 防路径穿越：只保留字母数字下划线短横线
        safe = "".join(c for c in safe if c.isalnum() or c in "_-")[:64] or "anon"
        from app.config import DATA_DIR  # 延迟 import，reload config 后拿到最新值
        self.dir = Path(DATA_DIR) / "traces" / safe
        self._t0 = time.time()
        self._steps: list[dict] = []
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            self.path = self.dir / "steps.jsonl"
        except Exception:  # noqa: BLE001
            self.path = None

    def log(self, **fields) -> None:
        fields["ts"] = round(time.time(), 3)
        fields["elapsed_ms"] = int((time.time() - self._t0) * 1000)
        self._steps.append(fields)
        if self.path is None:
            return
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(fields, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001
            pass

    def summary(self, **extra) -> None:
        body = {
            "session_id": self.dir.name,
            "total_elapsed_ms": int((time.time() - self._t0) * 1000),
            "step_count": len(self._steps),
            "tool_calls": sum(1 for s in self._steps if s.get("type") == "tool_call"),
            **extra,
        }
        try:
            (self.dir / "summary.json").write_text(
                json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            pass

    @property
    def steps(self) -> list[dict]:
        return self._steps

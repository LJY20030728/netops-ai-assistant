"""当前注入故障的状态记录（供拓扑页可视化"演练中"状态）。

落盘位置：backend/data/fault_state.json
结构：{"frr1": {"ospf_cost": "eth0"}, "frr2": {"link_down": "eth0"}, "updated": "..."}
inject 时写入对应条目，recover 时删除，recover-all 清空。
"""
import json
import time
from pathlib import Path

from app.config import DATA_DIR

_STATE_FILE = DATA_DIR / "fault_state.json"


def _load() -> dict:
    if not _STATE_FILE.exists():
        return {}
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def mark_inject(device: str, fault: str, iface: str) -> None:
    """记录某设备注入了某故障。"""
    state = _load()
    state.setdefault(device, {})[fault] = iface
    _save(state)


def clear_recover(device: str, fault: str | None = None) -> None:
    """恢复故障：fault 为 None 清空该设备全部，否则只删对应 fault。"""
    state = _load()
    if device not in state:
        return
    if fault is None:
        del state[device]
    else:
        state[device].pop(fault, None)
        if not state[device]:
            del state[device]
    _save(state)


def clear_all() -> None:
    """一键恢复：清空全部。"""
    _save({})


def snapshot() -> dict:
    """返回 {device: {fault: iface}, ...}（不含 updated 元字段）。"""
    state = _load()
    return {k: v for k, v in state.items() if isinstance(v, dict)}


# ---------------------------------------------------------------- dry-run gate
# 结构：{"dry_runs": {"<device>:<fault>:<iface>": <unix_ts>, ...}}
_DRY_RUN_KEY = "dry_runs"
DRY_RUN_WINDOW_SEC = 60  # dry_run 后 60 秒内 inject 有效


def _key(device: str, fault: str, iface: str) -> str:
    return f"{device}:{fault}:{iface}"


def mark_dry_run(device: str, fault: str, iface: str) -> None:
    """记录一次 dry-run 预览（inject 前必须先调它）。"""
    state = _load()
    state.setdefault(_DRY_RUN_KEY, {})[_key(device, fault, iface)] = time.time()
    _save(state)


def has_fresh_dry_run(device: str, fault: str, iface: str, window: int = DRY_RUN_WINDOW_SEC) -> bool:
    """检查 60 秒内是否对同一 (device, fault, iface) 做过 dry-run。"""
    state = _load()
    dr = state.get(_DRY_RUN_KEY, {})
    ts = dr.get(_key(device, fault, iface))
    if ts is None:
        return False
    return (time.time() - float(ts)) <= window
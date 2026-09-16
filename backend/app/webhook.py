"""告警 webhook：注册外部回调，模拟设备告警时推送（含 Agent 诊断建议）。

- 注册：POST /api/webhook/register {url, name}
- 触发：POST /api/alert/trigger {alert, device, scenario}
- 存储：backend/data/webhooks.json（URL 白名单仅限 http/https）
- 投递记录：backend/data/webhook_deliveries.jsonl（便于验证与演示）
"""
import json
import time
import urllib.request
from pathlib import Path

from app.config import DATA_DIR

WEBHOOKS_FILE = DATA_DIR / "webhooks.json"
DELIVERIES_FILE = DATA_DIR / "webhook_deliveries.jsonl"

# 场景 → 根因摘要（与 devices.py 剧本对齐，供告警推送使用）
SCENARIO_SUMMARY = {
    "flapping": "端口 GE0/0/1 频繁 up/down（CRC 错误增长），OSPF 邻居随之抖动",
    "stp_loop": "二层环路导致广播风暴，STP TCN 频繁、接口利用率与 CPU 飙升",
    "arp_poison": "ARP 欺骗：网关 MAC 被篡改为 aabb-cc00-00ff，终端间歇性断网",
    "bgp_flap": "BGP 邻居 10.0.1.1 反复 Active/ConnectRetry，路由不稳定",
    "acl_deny": "ACL 3001 拒绝 icmp 至 10.0.1.2（12 次命中），业务 ping 不通",
}


def _load_webhooks() -> list[dict]:
    if not WEBHOOKS_FILE.exists():
        return []
    try:
        return json.loads(WEBHOOKS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _save_webhooks(items: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WEBHOOKS_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def register(url: str, name: str) -> dict:
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("webhook URL 必须是 http/https")
    items = _load_webhooks()
    # 同 URL 去重（幂等）
    items = [w for w in items if w["url"] != url]
    items.append({"url": url, "name": name, "registered": time.strftime("%Y-%m-%d %H:%M:%S")})
    _save_webhooks(items)
    return {"ok": True, "webhooks": items}


def list_webhooks() -> list[dict]:
    return _load_webhooks()


def deliver(alert: str, device: str, scenario: str) -> dict:
    """向全部已注册 webhook 推送告警（含场景根因摘要），记录投递结果。"""
    hooks = _load_webhooks()
    if not hooks:
        return {"ok": False, "delivered": 0, "message": "未注册任何 webhook"}
    payload = {
        "event": "netops.alert",
        "alert": alert,
        "device": device,
        "scenario": scenario,
        "summary": SCENARIO_SUMMARY.get(scenario, ""),
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "NetOps AI Assistant",
    }
    results = []
    for h in hooks:
        try:
            req = urllib.request.Request(
                h["url"],
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                status = resp.status
                body = resp.read().decode("utf-8", errors="replace")[:200]
            ok = True
        except Exception as exc:  # noqa: BLE001
            ok, status, body = False, 0, str(exc)[:200]
        results.append({"webhook": h["url"], "ok": ok, "status": status, "response": body})
        # 投递记录
        DELIVERIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with DELIVERIES_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"payload": payload, "result": results[-1]}, ensure_ascii=False) + "\n")
    return {"ok": all(r["ok"] for r in results), "delivered": len(results), "results": results}

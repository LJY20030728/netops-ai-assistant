"""Webhook 注册与告警接收路由。"""
import json
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import DATA_DIR
from app.agent import agent as agent_runner
from app.security import audit
from app.security.auth import require_role
from app import webhook as webhook_svc

router = APIRouter(prefix="/api", tags=["alert"])

ALERT_DIAG_FILE = DATA_DIR / "alert_diagnoses.jsonl"


class WebhookBody(BaseModel):
    url: str = Field(..., min_length=5, max_length=512)
    name: str = Field(default="webhook", max_length=64)


class AlertBody(BaseModel):
    alert: str = Field(..., min_length=1, max_length=128)
    device: str = Field(default="core-sw-1", max_length=64)
    scenario: str = Field(default="flapping", max_length=32)


class AlertReceiveBody(BaseModel):
    alert: str = ""
    device: str = ""
    alerts: list[dict] = []


@router.get("/webhook")
async def webhook_list(role: str = Depends(require_role("viewer"))):
    return {"ok": True, "webhooks": webhook_svc.list_webhooks()}


@router.post("/webhook/register")
async def webhook_register(body: WebhookBody, role: str = Depends(require_role("admin"))):
    try:
        result = webhook_svc.register(body.url, body.name)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    audit.log("webhook", actor=role, action="webhook.register", detail=body.url)
    return result


@router.post("/alert/trigger")
async def alert_trigger(body: AlertBody, role: str = Depends(require_role("operator"))):
    result = webhook_svc.deliver(body.alert, body.device, body.scenario)
    audit.log("alert", actor=role, action="alert.trigger",
              detail=json.dumps({"alert": body.alert, "scenario": body.scenario,
                                 "delivered": result.get("delivered", 0)}, ensure_ascii=False))
    return result


@router.post("/alert/receive")
async def alert_receive(body: AlertReceiveBody):
    text = body.alert.strip()
    if not text and body.alerts:
        a = body.alerts[0] or {}
        labels = a.get("labels", {}) or {}
        ann = a.get("annotations", {}) or {}
        text = f"[告警] {labels.get('alertname', '')} 实例={labels.get('instance', '')} 摘要={ann.get('summary', '')}"
    text = text.strip()
    if not text:
        return {"ok": False, "message": "无告警内容（需 alert 字段或 alerts 数组）"}

    prompt = f"收到运维告警：{text}。请按排障流程分析可能根因，给出处置建议与验证步骤。"
    answer_parts: list[str] = []
    try:
        async for ev in agent_runner.run_agent(prompt, [], role="operator"):
            if ev.get("type") == "delta":
                answer_parts.append(ev.get("content", ""))
            if ev.get("type") == "tool":
                audit.log("alert", actor="operator", action=ev.get("tool", ""),
                          detail=json.dumps({"alert": text[:40], "args": ev.get("args"),
                                             "ok": ev.get("ok")}, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        answer_parts.append(f"诊断异常: {exc}")

    answer = "".join(answer_parts)
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "alert": text,
           "device": body.device or "core-sw-1", "diagnosis": answer}
    ALERT_DIAG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ALERT_DIAG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    audit.log("alert", actor="operator", action="alert.receive", detail=text[:80])
    return {"ok": True, "alert": text, "diagnosis": answer[:800]}


@router.get("/alert/list")
async def alert_list(limit: int = 20):
    out: list[dict] = []
    if ALERT_DIAG_FILE.exists():
        for line in ALERT_DIAG_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    out = out[-limit:][::-1]
    return {"alerts": out, "count": len(out)}

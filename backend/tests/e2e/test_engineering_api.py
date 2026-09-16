# -*- coding: utf-8 -*-
"""优化5/6 工程化与产品化 API 测试（依赖 8000 服务运行）：
会话持久化（保存/读取/列表）→ 报告导出（HTML 生成与访问）→ webhook 注册/触发/投递记录。
运行：cd backend; ..\\.venv\\Scripts\\python.exe -X utf8 tests\\test_engineering_api.py
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0
SID = "test-eng-" + str(int(time.time() * 1000))


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


def post(path: str, body: dict | None = None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_sessions():
    print("== 会话持久化 ==")
    # 直接写一条 user 消息（模拟 chat 落盘）
    from app import session_store  # noqa: E402

    session_store.append(SID, "user", "测试消息")
    session_store.append(SID, "assistant", "测试回答")
    d = get(f"/api/session/{SID}")
    check("读取会话：ok", d.get("ok") is True)
    check("读取会话：2 条消息", len(d.get("messages", [])) == 2)
    check("消息角色正确", [m["role"] for m in d.get("messages", [])] == ["user", "assistant"])
    lst = get("/api/sessions")
    check("列表含当前会话", any(s["session_id"] == SID for s in lst.get("sessions", [])))
    # 非法 session_id 防护
    req = urllib.request.Request(BASE + "/api/session/..%2F..%2Fetc", method="GET")
    try:
        urllib.request.urlopen(req, timeout=10)
        check("非法 session_id 被拒", False, "未拒绝")
    except urllib.error.HTTPError as exc:
        check("非法 session_id 被拒（HTTP " + str(exc.code) + "）", exc.code in (400, 404, 422))


def test_report():
    print("== 报告导出 ==")
    d = get(f"/api/report/{SID}")
    check("导出成功", d.get("ok") is True, str(d)[:120])
    check("报告文件已落盘", d.get("report_url", "").endswith("/file"), str(d)[:120])
    p = Path(d.get("file", ""))
    check("文件存在且非空", p.exists() and p.stat().st_size > 500, str(p))
    html = p.read_text(encoding="utf-8")
    check("含中文标题", "故障排障报告" in html)
    check("含会话内容", "测试消息" in html and "测试回答" in html)
    # 通过 URL 可访问
    with urllib.request.urlopen(BASE + d["report_url"], timeout=15) as resp:
        body = resp.read().decode("utf-8")
        check("report_url 可访问", resp.status == 200 and "NetOps" in body)


def test_webhook():
    print("== 告警 webhook ==")
    # 注册：指向本服务自身不存在的端点会投递失败，先注册一个本地 echo（用 httpbin 风格不可靠）
    # 改为：注册本服务 /api/health（POST 会 405），验证"已投递但失败"也能记录；再验证投递记录存在。
    d = post("/api/webhook/register", {"url": f"{BASE}/api/health", "name": "test-hook"})
    check("注册成功", d.get("ok") is True, str(d)[:120])
    lst = get("/api/webhook")
    check("列表包含新 hook", any(w["url"] == f"{BASE}/api/health" for w in lst.get("webhooks", [])))
    # 触发告警（投递到 /api/health 会失败，但投递记录必须写入）
    d = post("/api/alert/trigger", {"alert": "端口抖动告警", "device": "core-sw-1", "scenario": "flapping"})
    check("触发返回结构", "delivered" in d and "results" in d, str(d)[:150])
    rec = Path("data/webhook_deliveries.jsonl")
    check("投递记录已落盘", rec.exists() and rec.stat().st_size > 100)
    last = rec.read_text(encoding="utf-8").strip().splitlines()[-1]
    check("记录含告警摘要", "端口 GE0/0/1" in last, last[:120])
    check("记录含场景根因", "flapping" in last)


if __name__ == "__main__":
    import sys as _sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    test_sessions()
    test_report()
    test_webhook()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)

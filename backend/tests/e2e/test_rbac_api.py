# -*- coding: utf-8 -*-
"""RBAC 端到端测试（auth 实例，127.0.0.1:8001）。

覆盖：无令牌=viewer / viewer 令牌 / operator 令牌 / admin 令牌
- Agent 设备工具权限（viewer 禁用、operator 可用）
- /api/kb/ingest 仅 admin
"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8001"
PASS = 0
FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {extra}")


def post_chat(message, token=None):
    body = json.dumps({"message": message, "history": []}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}/api/chat", data=body, headers=headers)
    last = None
    for _ in range(2):  # 对瞬态连接重置做一次重试
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read().decode("utf-8")
        except (urllib.error.URLError, ConnectionResetError) as exc:
            last = exc
    raise last


def parse_sse(text):
    return [
        json.loads(line[6:])
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


def ingest(token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}/api/kb/ingest", method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None


DEVICE_Q = "从 core-sw-1 检查 GE0/0/1 端口状态"

print("== 1. 无令牌（默认 viewer） ==")
evs = parse_sse(post_chat(DEVICE_Q))
tool_evs = [e for e in evs if e["type"] == "tool"]
check("viewer 无权限调用设备工具", tool_evs and not tool_evs[0]["ok"], tool_evs)
check("viewer 工具报错含权限", tool_evs and "无权" in tool_evs[0]["result"], tool_evs)
status, _ = ingest()
check("viewer 调 ingest 被 403", status == 403, status)

print("== 2. viewer 令牌 ==")
evs = parse_sse(post_chat(DEVICE_Q, token="viewer-tok"))
tool_evs = [e for e in evs if e["type"] == "tool"]
check("viewer 令牌调设备工具被拒", tool_evs and not tool_evs[0]["ok"], tool_evs)
status, _ = ingest("viewer-tok")
check("viewer 令牌 ingest 403", status == 403, status)

print("== 3. operator 令牌 ==")
evs = parse_sse(post_chat(DEVICE_Q, token="op-tok"))
tool_evs = [e for e in evs if e["type"] == "tool"]
check("operator 可调设备工具", tool_evs and tool_evs[0]["ok"], tool_evs)
status, _ = ingest("op-tok")
check("operator ingest 403（非 admin）", status == 403, status)

print("== 4. admin 令牌 ==")
evs = parse_sse(post_chat("日常巡检应该关注哪些指标", token="admin-tok"))
types = [e["type"] for e in evs]
check("admin 正常对话", "done" in types and "sources" in types, types)
status, body = ingest("admin-tok")
check("admin ingest 200", status == 200 and body.get("total_chunks", 0) >= 19, (status, body))
evs = parse_sse(post_chat(DEVICE_Q, token="admin-tok"))
tool_evs = [e for e in evs if e["type"] == "tool"]
check("admin 可调设备工具", tool_evs and tool_evs[0]["ok"], tool_evs)

print(f"\n结果：{PASS} 通过，{FAIL} 失败")
sys.exit(1 if FAIL else 0)

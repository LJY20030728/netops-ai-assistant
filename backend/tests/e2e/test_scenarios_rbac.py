# -*- coding: utf-8 -*-
"""场景切换 RBAC 权限测试（8001 auth 实例）：viewer 禁切场景，admin 可切。"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8001"
TOKENS = {"viewer": "viewer-tok", "operator": "op-tok", "admin": "admin-tok"}

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


def post(path, body, token):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {}


def get(path, token):
    req = urllib.request.Request(BASE + path, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {}


def main():
    # 无 token
    req = urllib.request.Request(BASE + "/api/sim/scenario", method="POST",
                                 data=json.dumps({"scenario": "stp_loop"}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=15)
        check("无 token 被拒", False, "应 401/403")
    except urllib.error.HTTPError as e:
        check("无 token 被拒", e.code in (401, 403), f"code={e.code}")

    # viewer 可看场景但不能切
    s, _ = get("/api/sim/scenario", TOKENS["viewer"])
    check("viewer 可查看场景", s == 200, f"code={s}")
    s, body = post("/api/sim/scenario", {"scenario": "stp_loop"}, TOKENS["viewer"])
    check("viewer 禁切场景", s == 403, f"code={s} body={body}")

    # operator 也不能切（场景切换属于管理操作，仅 admin）
    s, _ = post("/api/sim/scenario", {"scenario": "stp_loop"}, TOKENS["operator"])
    check("operator 禁切场景", s == 403, f"code={s}")

    # admin 可切
    s, body = post("/api/sim/scenario", {"scenario": "stp_loop"}, TOKENS["admin"])
    check("admin 可切场景", s == 200 and body.get("ok") is True and body.get("scenario") == "stp_loop", f"code={s} body={body}")

    # 恢复
    post("/api/sim/scenario", {"scenario": "flapping"}, TOKENS["admin"])

    print(f"\n结果：{PASS} 通过，{FAIL} 失败")
    sys.exit(1 if FAIL else 0)


main()

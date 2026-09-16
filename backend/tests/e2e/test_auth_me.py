# -*- coding: utf-8 -*-
"""M5-2 认证令牌接入：/api/auth/me 端点在默认与鉴权模式下的行为验证。"""
import json
import sys
import urllib.error
import urllib.request


def me(base, token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + "/api/auth/me", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {}


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


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"

    # 无 token（鉴权开启）
    s, m = me(base)
    check("鉴权模式无 token → 未认证 viewer", m.get("authenticated") is False and m.get("role") == "viewer", str(m))

    # 无效 token
    s, m = me(base, "wrong-tok")
    check("无效 token → 未认证", m.get("authenticated") is False, str(m))

    # 各角色 token
    for tok, role in [("viewer-tok", "viewer"), ("op-tok", "operator"), ("admin-tok", "admin")]:
        s, m = me(base, tok)
        check(f"{role} token → authenticated role={role}", m.get("authenticated") is True and m.get("role") == role, str(m))

    # 鉴权开启标记
    s, m = me(base, "admin-tok")
    check("auth_enabled=true 标记", m.get("auth_enabled") is True, str(m))

    # viewer 请求场景切换应 403（配合前端角色裁剪）
    req = urllib.request.Request(
        base + "/api/sim/scenario",
        data=json.dumps({"scenario": "stp_loop"}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer viewer-tok"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        check("viewer 切场景被拒(403)", False, "不应成功")
    except urllib.error.HTTPError as e:
        check("viewer 切场景被拒(403)", e.code == 403, f"code={e.code}")

    # admin 可切
    req = urllib.request.Request(
        base + "/api/sim/scenario",
        data=json.dumps({"scenario": "stp_loop"}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer admin-tok"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = json.loads(r.read().decode("utf-8"))
            check("admin 切场景成功", body.get("ok") is True and body.get("scenario") == "stp_loop", str(body))
    except urllib.error.HTTPError as e:
        check("admin 切场景成功", False, f"code={e.code}")
    # 恢复
    req = urllib.request.Request(
        base + "/api/sim/scenario",
        data=json.dumps({"scenario": "flapping"}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer admin-tok"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=10)

    print(f"\n结果：{PASS} 通过，{FAIL} 失败")
    sys.exit(1 if FAIL else 0)


main()

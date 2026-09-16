# -*- coding: utf-8 -*-
"""场景切换 HTTP API 测试：GET/POST /api/sim/scenario、health 字段、devices 字段。"""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000"

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


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    # health 字段
    h = get("/api/health")
    check("health 含 sim_scenario", "sim_scenario" in h and h["device_mode"] == "simulate", str(h.get("sim_scenario")))

    # GET 当前场景
    s0 = get("/api/sim/scenario")
    check("GET 场景返回当前值", s0.get("scenario") in ["flapping", "stp_loop", "arp_poison", "bgp_flap", "acl_deny"], str(s0))
    check("available 含 5 场景", set(s0.get("available", [])) == {"flapping", "stp_loop", "arp_poison", "bgp_flap", "acl_deny"}, str(s0.get("available")))

    # POST 切换 5 场景
    for sc in ["stp_loop", "arp_poison", "bgp_flap", "acl_deny", "flapping"]:
        r = post("/api/sim/scenario", {"scenario": sc})
        check(f"POST 切换 {sc}", r.get("ok") is True and r.get("scenario") == sc, str(r))
        # 切换后 GET 验证
        g = get("/api/sim/scenario")
        check(f"GET 确认 {sc}", g.get("scenario") == sc, str(g))

    # 非法场景
    r = post("/api/sim/scenario", {"scenario": "not_exist"})
    check("非法场景被拒", r.get("ok") is False and r.get("message"), str(r))

    # devices 接口含场景
    d = get("/api/devices")
    check("devices 含 scenario", "scenario" in d and d["mode"] == "simulate", str(d.get("scenario")))
    check("devices 3 台", len(d.get("devices", [])) == 3, str(len(d.get("devices", []))))

    print(f"\n结果：{PASS} 通过，{FAIL} 失败")
    sys.exit(1 if FAIL else 0)


main()

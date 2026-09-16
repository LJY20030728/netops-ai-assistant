# -*- coding: utf-8 -*-
"""验证入库幂等性 + 安全 API 冒烟（临时脚本）。"""
import json
import urllib.request

BASE = "http://127.0.0.1:8000"

# 1) 调 ingest 两次，chunks 应保持不变（幂等）
def ingest():
    req = urllib.request.Request(f"{BASE}/api/kb/ingest", method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))

def chunks():
    with urllib.request.urlopen(f"{BASE}/api/health", timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))["kb_chunks"]

c0 = chunks()
r1 = ingest()
c1 = chunks()
r2 = ingest()
c2 = chunks()
print(f"before={c0}  after1={c1} (added {r1.get('chunks')})  after2={c2} (added {r2.get('chunks')})")
print("PASS 幂等" if c1 == c2 and c1 <= c0 + 19 else "FAIL 幂等", flush=True)

# 2) 入库替换语义回归（历史 bug：add_chunks 内 recs 重绑定局部变量，
#    self._records 未更新导致 _save 写旧数据，同 id 文本变化从未真正替换）
import sys
sys.path.insert(0, ".")
from app.rag.store import get_backend, add_chunks

store = get_backend()
before = store.records()
if before:
    cid = before[0]["id"]
    orig_text = before[0]["text"]
    mutated = orig_text + "\n【回归标记】"
    n1 = add_chunks([{"id": cid, "text": mutated, "metadata": before[0]["metadata"]}])
    replaced = any(r["id"] == cid and "【回归标记】" in r["text"] for r in get_backend().records())
    n2 = add_chunks([{"id": cid, "text": orig_text, "metadata": before[0]["metadata"]}])
    final = get_backend().records()
    restored = any(r["id"] == cid and "【回归标记】" not in r["text"] for r in final)
    print(f"replace: n1={n1} replaced={replaced} restored={restored} count={len(final)}")
    print("PASS 替换" if (n1 == 1 and replaced and restored and len(final) == len(before)) else "FAIL 替换", flush=True)
else:
    print("SKIP 替换（空库）", flush=True)

# -*- coding: utf-8 -*-
"""Agent /api/chat SSE 端到端测试（临时）：观察工具调用链 + 最终回答。"""
import json
import urllib.request

BASE = "http://127.0.0.1:8000"


def sse_chat(message: str):
    body = json.dumps({"message": message, "history": []}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/api/chat", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        buf = ""
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            buf += chunk.decode("utf-8", "replace")
            while "\n\n" in buf:
                block, buf = buf.split("\n\n", 1)
                line = block.strip()
                if not line.startswith("data: "):
                    continue
                yield json.loads(line[6:])


if __name__ == "__main__":
    q = "从 core-sw-1 检查到 10.0.1.2 的连通性，并排查 OSPF 邻居为什么 DOWN，给出处置建议"
    print("Q:", q)
    answer = ""
    for ev in sse_chat(q):
        t = ev.get("type")
        if t == "tool":
            print(f"[tool] {ev.get('tool')} args={json.dumps(ev.get('args'), ensure_ascii=False)} ok={ev.get('ok')}")
            print(f"   result: {(ev.get('result') or '').replace(chr(10),' ')[:160]}")
        elif t == "delta":
            answer += ev.get("content", "")
        elif t == "error":
            print("ERROR:", ev.get("message"))
        elif t == "done":
            print("== done ==")
    print("== answer (len %d) ==" % len(answer))
    print(answer[:1800])

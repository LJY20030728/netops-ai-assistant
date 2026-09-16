# -*- coding: utf-8 -*-
"""/api/chat SSE 端到端测试（临时）。"""
import json
import urllib.request

BASE = "http://127.0.0.1:8000"


def sse_chat(message: str):
    body = json.dumps({"message": message, "history": []}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
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
                data = json.loads(line[6:])
                yield data


if __name__ == "__main__":
    q = "核心交换机 SW-1 的 1/0/1 端口反复 up/down，请给出排查步骤"
    print("Q:", q)
    sources = None
    answer = ""
    for ev in sse_chat(q):
        t = ev.get("type")
        if t == "sources":
            sources = ev.get("sources")
            print("== sources ==")
            for s in sources:
                print(f"   {s}")
        elif t == "delta":
            answer += ev.get("content", "")
        elif t == "error":
            print("ERROR:", ev.get("message"))
        elif t == "done":
            print("== done ==")
    print("== answer (tail) ==")
    print(answer[-500:])
    print("== answer length:", len(answer))

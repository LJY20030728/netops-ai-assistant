# -*- coding: utf-8 -*-
"""RAG 检索质量自测脚本（临时）。"""
import sys

sys.path.insert(0, ".")
from app.rag import store  # noqa: E402

queries = [
    "核心交换机端口反复 up/down 怎么排查",
    "OSPF 邻居卡在 ExStart 状态原因",
    "光纤接收光功率过低导致误码",
    "交换机接终端端口为什么要开 portfast",
    "BGP 邻居一直 Active 状态",
]
for q in queries:
    hits = store.search(q, 3)
    print("Q:", q)
    for h in hits:
        preview = h["text"][:45].replace("\n", " ")
        print(f"   {h['score']:.3f}  {h['metadata']['source']}  | {preview}")
    print()

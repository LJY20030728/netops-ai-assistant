# -*- coding: utf-8 -*-
"""检索质量抽查：新场景关键词应命中对应新手册。

expect 支持 tuple：复合意图查询（如同一故障因果链的多个主题）可接受多个等价文档。
"""
import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(line_buffering=True)

from app.rag.retrieval import hybrid_retrieve

CASES = [
    ("接口 up 但 ping 超时 被 ACL 拦截", "ACL访问控制列表配置与排障.md"),
    # 复合歧义查询：环路→广播风暴→CPU 高占用是同一因果链，top3 命中链上任一文档即正确
    ("交换机 CPU 占用率高 广播风暴 环路",
     ("设备CPU高占用排查.md", "网络广播风暴定位与处置.md", "STP生成树与环路排查.md", "case-007.md")),
    ("ARP 冲突 IP 地址 MAC 变了", "ARP冲突与欺骗专项排查.md"),
    ("BGP 邻居 Active 状态 起不来", "BGP路由振荡与路由策略排障.md"),
    ("终端获取不到 IP DHCP", "DHCP无法获取IP地址排查.md"),
    ("NAT 地址转换 外网访问不了", "NAT地址转换配置与排障.md"),
    ("防火墙会话表 安全策略 deny", "防火墙安全策略与会话表排查.md"),
    ("VRRP 主备切换 网关不通", "VRRP网关冗余故障排查.md"),
]

PASS = 0
FAIL = 0
for q, expect in CASES:
    hits = hybrid_retrieve(q, 5)
    sources = [h["metadata"].get("source", "") for h in hits]
    exp_set = {expect} if isinstance(expect, str) else set(expect)
    hit = bool(exp_set & set(sources[:3]))
    if hit:
        PASS += 1
        print(f"[PASS] {q[:22]}... -> {sources[0]}")
    else:
        FAIL += 1
        print(f"[FAIL] {q[:22]}... 期望 {exp_set}，实际 top3={sources[:3]}")

print(f"\n检索质量：{PASS} 通过，{FAIL} 失败")
sys.exit(1 if FAIL else 0)

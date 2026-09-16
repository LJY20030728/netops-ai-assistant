# IPv6双栈与地址分配排障

## 典型症状
v4/v6 双栈环境下用户拿到 IPv6 地址但访问 v6 业务不通；或 RA 报文导致主机地址频繁变化。

## 原理速记
IPv6 依赖 RA（路由器通告）下发前缀，邻居发现 ND 代替 ARP；双栈设备需同时维护 v4/v6 路由表与 FIB。

## 排查步骤
- `display ipv6 interface brief` —— 看接口是否拿到 global unicast 前缀（2000::/3）
- `display ndp interface GigabitEthernet0/0/1` —— 看邻居表有无对端 MAC，是否 stale/incomplete
- `display ipv6 routing-table` —— 看默认路由 ::/0 是否存在、出接口正确
- `ping ipv6 2001:db8::1` —— 源地址是否选对（多前缀场景易选错源）

## 常见根因
RA 抑制未开导致终端随机地址；前缀长度与对端掩码不一致；ND 被防火墙过滤。

## 处置与验证
undo ipv6 nd ra halt 按需放开；确认前缀/掩码两端一致；验证 ping ipv6 双向通且路由稳定。

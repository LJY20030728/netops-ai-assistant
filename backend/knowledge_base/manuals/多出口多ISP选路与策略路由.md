# 多出口多ISP选路与策略路由

## 典型症状
多运营商出口环境下用户流量走错出口，访问某 ISP 业务慢；回程路由不对称。

## 原理速记
策略路由 PBR 按源地址/应用强制指定下一跳；多出口需配合 BGP 引入或静态路由 + track 联动。

## 排查步骤
- `display ip policy-based-route` —— 看策略节点、if-match、apply next-hop
- `display ip routing-table` —— 看实际选路
- `traceroute 目标` —— 看出口路径

## 常见根因
PBR 与路由表优先级冲突（PBR 先于路由表）；track 联动未配致主出口断后仍走死下一跳。

## 处置与验证
按源/应用正确走对应出口；主出口断后 track 自动切备；回程对称。

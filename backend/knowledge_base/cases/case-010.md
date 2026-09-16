# 案例010：BGP 邻居一直 Active（地址族未激活）

【告警类型】BGP_NEIGHBOR_DOWN
【来源】reference（参考思科社区 BGP address-family 排障案例改编）

## 工单现象
"bgp 邻居起不来，一直 active，查了地址能通"。与对端 AS 建立 eBGP 邻居，TCP 可达（ping 通）但邻居状态停在 Active，无法进入 Established。

## 排查过程
1. `display bgp peer`：邻居状态 Active，Last down reason 为 OpenSent/Active 反复；
2. 确认两端 AS 号、邻居地址、update-source 配置正确；
3. 检查地址族：IPv4 unicast 地址族下未 `neighbor X activate`，导致路由不交换但邻居仍未建立（对端等待能力协商）；
4. 在地址族下激活邻居后，状态立即转为 Established。

## 根因
BGP 邻居已在 address-family 外配置，但未在 ipv4 unicast 地址族内 activate，能力协商不完整导致邻居停留在 Active。

## 处置
配置 `address-family ipv4 unicast` + `neighbor X activate`；新增 BGP 邻居的变更检查单增加"地址族激活"项。

# PIM-SM组播路由排障

## 典型症状
组播视频业务部分用户收不到；RP 学习不到；(S,G) 表项缺失。

## 原理速记
PIM-SM 用 RP（汇聚点）转发组播流；末端路由器通过 IGMP 加入组；RP 与 DR 角色决定转发路径。

## 排查步骤
- `display pim rp-info` —— 看 RP 是否静态/BSR 学到
- `display pim routing-table` —— 看 (*,G) 与 (S,G) 表项；入接口/出接口列表
- `display igmp group` —— 看用户侧接口是否 join 了组

## 常见根因
RP 地址全网不一致；下游未使能 igmp；TTL 阈值或组播 ACL 过滤。

## 处置与验证
全网 RP 一致；(*,G)/(S,G) 表项正确；用户端收到组播流。

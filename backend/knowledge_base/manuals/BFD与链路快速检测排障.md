# BFD与链路快速检测排障

## 典型症状
主链路断了但路由收敛慢（秒级）；BFD 会话 Down 但未联动 OSPF/BGP 降级。

## 原理速记
BFD 在毫秒级检测链路，与 OSPF/BGP 联动：检测到故障立即触发协议降级，无需等 Hello/Hold。

## 排查步骤
- `display bfd session all` —— 看会话状态 Up；检测时间 multiplier*interval 是否符合设计
- `display ospf interface` —— 看接口下是否绑定 bfd；display bgp peer 看 bfd 使能
- `shutdown 主接口模拟` —— 抓 OSPF/BGP 收敛时间是否 < 1s

## 常见根因
一端使能 BFD 另一端未使能；间隔参数两端不匹配；多跳 BFD 与直连 BFD 混淆。

## 处置与验证
两端统一 interval/multiplier；接口下 ospf/bgp bfd enable；断链后协议秒级收敛。

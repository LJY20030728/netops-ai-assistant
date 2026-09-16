# OSPF-Stub与NSSA区域配置

## 症状
末端区域想减少 LSA 数量，但配错 NSSA 后外部路由丢失。

## 排查
- `display ospf abr` —— 确认 ABR
- `area 1 stub / nssa` —— Stub 禁外部，NSSA 允许
- `display ospf routing-table` —— 看缺省路由

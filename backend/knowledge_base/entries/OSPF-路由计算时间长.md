# OSPF-路由计算时间长

## 症状
路由收敛慢。

## 排查
- `display ospf spf-statistics` —— 看 SPF 耗时
- `SPF 智能定时器` —— 调 throttling

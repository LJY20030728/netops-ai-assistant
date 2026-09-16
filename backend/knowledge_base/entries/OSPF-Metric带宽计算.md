# OSPF-Metric带宽计算

## 症状
OSPF cost 与带宽关系不明。

## 排查
- `display ospf interface` —— 看 cost
- `BW 100M=1` —— 参考带宽/带宽
- `auto-cost reference-bandwidth` —— 改参考值

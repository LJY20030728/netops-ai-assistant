# OSPF-邻居卡在ExStart

## 症状
OSPF 邻居一直卡在 ExStart/Exchange。

## 排查
- `display ospf peer` —— 看状态
- `检查 MTU 两端一致` —— 不同 MTU 卡 DBD
- `检查 Router-ID 冲突` —— 同 RID 必卡

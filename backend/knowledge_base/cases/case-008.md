# 案例008：OSPF 邻居卡在 ExStart（MTU 不匹配）

【告警类型】OSPF_NEIGHBOR_DOWN
【来源】reference（参考华为企业技术支持社区 OSPF MTU 排障案例改编）

## 工单现象
"ospf 邻居怎么都起不来，重启路由器也没用"。新增互联链路后 OSPF 邻居始终无法进入 Full 状态，日志显示反复处于 ExStart/Exchange。

## 排查过程
1. `display ospf peer`：邻居状态卡在 ExStart，不向前推进；
2. `display ospf error`：DD 报文相关错误计数增长；
3. 两端接口 MTU 不一致（一端 1500、一端 1400）：OSPF 的 DD 报文在 MTU 大的一端被丢弃；
4. 统一两端接口 MTU 后 `reset ospf process`，邻居恢复 Full。

## 根因
链路两端接口 MTU 不匹配，导致 OSPF 的 DD 报文无法通过（MTU 校验失败），邻居建立卡在 ExStart 阶段。

## 处置
统一互联接口 MTU（或配置 `ospf mtu-ignore` 并明确风险）；变更检查单增加"两端 MTU 一致性"校验。

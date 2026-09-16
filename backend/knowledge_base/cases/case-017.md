# 案例017：交换机 CPU 居高不下（协议震荡）

【告警类型】CPU_HIGH
【来源】simulated（模拟工单，按常见故障模式编写）

## 工单现象
"交换机 cpu 一直 90 多，不知道啥进程占的"。核心交换机 CPU 持续 90%+，业务偶发中断，管理面响应迟缓。

## 排查过程
1. `display cpu-usage`：CPU 利用率 93%；
2. `display cpu-usage history`：高占用持续数小时非瞬时；
3. `display process cpu`：OSPF/BGP 进程占用最高——路由协议频繁计算；
4. 关联日志：OSPF 邻居反复震荡触发 SPF 频繁计算；修复邻居震荡后 CPU 回落。

## 根因
路由协议震荡（OSPF 邻居反复 up/down）触发 SPF 频繁重算，CPU 被协议进程打满。

## 处置
先修邻居震荡根因（MTU/定时器/物理层）；对管理面启用 CPU 保护与协议抑制；建立 CPU 基线告警。

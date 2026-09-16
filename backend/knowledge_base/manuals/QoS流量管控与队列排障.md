# QoS流量管控与队列排障

## 典型症状
已配置限速/优先级但视频会议仍卡顿；关键业务未优先转发；队列丢包但接口统计无错包。

## 原理速记
QoS 流分类→流行为（CAR 限速/队列调度/丢弃策略）→策略应用；拥塞发生在出队列而非物理错包。

## 排查步骤
- `display qos policy interface GigabitEthernet0/0/1` —— 看应用方向、命中计数器
- `display qos queue statistics interface` —— 看各队列 Packets/Drop，定位哪队列丢
- `display traffic policy statistics` —— 看分类规则命中数，是否分类不准

## 常见根因
策略应用方向错（应出方向配成入方向）；分类 ACL 未命中；队列调度模式缺省 WFQ 抢占。

## 处置与验证
策略出方向应用；分类命中计数增长；拥塞队列 Drop 下降，关键业务时延改善。

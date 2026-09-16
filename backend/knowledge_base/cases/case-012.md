# 案例012：BGP 邻居反复震荡（keepalive/hold 定时器不一致）

【告警类型】BGP_NEIGHBOR_DOWN
【来源】simulated（模拟工单，按常见故障模式编写）

## 工单现象
"业务访问慢，检查发现 bgp 邻居一会儿 established 一会儿 down，keepalive 时间两边不一样"。对外业务间歇性中断，路由表反复波动。

## 排查过程
1. `display bgp peer`：邻居状态在 Established/Down 之间反复，Last down reason 为 Hold Timer Expired；
2. 核对两端 hold 时间：一端 hold=180s，对端 hold=90s，链路瞬时拥塞时 keepalive 报文延迟超时；
3. 统一 hold/keepalive 定时器（或显式配置 `timers bgp keepalive 60 hold 180`）；
4. 定时器统一后邻居稳定在 Established。

## 根因
两端 BGP hold 定时器不一致，叠加链路拥塞导致 keepalive 超时，邻居反复震荡。

## 处置
与对端协商统一 BGP 定时器；对拥塞链路配置 QoS 保障 BGP 控制报文优先转发。

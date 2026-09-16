# 案例005：STP 拓扑变更频繁（边缘端口抖动）

【告警类型】STP_TOPOLOGY_CHANGE
【来源】simulated（模拟工单，按常见故障模式编写）

## 工单现象
终端老掉线，查了 stp 发现拓扑变更次数特别多，接入端口一直 up down。全网设备 CPU 上升，业务偶发中断。

## 排查过程
1. `display stp topology-change`：Topology changes 计数在短时间内暴涨；
2. `display stp brief`：大量接入端口触发 TC（拓扑变更）；
3. 定位到是会议室网口设备反复插拔/抖动，触发了 TC 报文全网泛洪；
4. 将接入端口配置为边缘端口（edge-port）+ BPDU 保护。

## 根因
非边缘接入端口频繁 up/down 触发 STP 拓扑变更，TC 报文泛洪导致全网 MAC 表反复刷新、业务中断。

## 处置
接入端口统一配置 edge-port + BPDU guard；边缘端口抖动不再触发 TC。

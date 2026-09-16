# 设备 CPU 高占用排查

## 问题现象
设备 CPU 利用率持续高位（>80%），转发性能下降、管理面响应慢（ping 设备地址丢包、SSH 卡顿），业务时通时断。

## 排查步骤
1. 查看 CPU 利用率与历史峰值：
   ```
   display cpu-usage
   display cpu-usage history
   ```
   关注：当前值、峰值、User/System/Interrupt 占比。System 或 Interrupt 高通常与协议处理/中断风暴相关。

2. 查看当前占用 CPU 的进程：
   ```
   display cpu-usage task
   ```
   异常时常见：STP、OSPF、BGP 等协议进程高，或路由协议计算频繁（拓扑震荡）。

3. 检查协议邻居与拓扑震荡：
   ```
   display ospf peer
   display bgp peer
   display stp topology-change
   ```
   - 邻居频繁 up/down 会触发大量协议重算；
   - STP 拓扑变化计数持续增长说明二层存在震荡/环路。

4. 检查流量冲击与广播风暴：
   ```
   display interface brief
   display interface <端口>
   ```
   - 接口利用率异常高、广播/组播计数暴涨；
   - 入向错误计数（inErrors）增长说明有异常流量。

5. 查看日志确认异常事件：
   ```
   display logbuffer | include CPU|DEFEND
   ```
   设备防攻击（攻击防范）日志会记录被丢弃的攻击报文。

## 常见根因与处置
| 根因 | 处置 |
|---|---|
| 二层环路/广播风暴 | 剪断环路，开启 STP，限制广播域 |
| 协议邻居震荡 | 修复底层链路/配置，稳定邻居关系 |
| 攻击流量冲击 CPU | 开启攻击防范（car / 限速），ACL 过滤 |
| 配置过多导致计算量大 | 精简路由策略/ACL，评估设备容量 |
| 硬件老化 | 更换设备或扩容 |

## 注意事项
CPU 高是"结果"不是"原因"，一定要继续往协议震荡、环路、攻击三个方向取证，找到触发源再处置。

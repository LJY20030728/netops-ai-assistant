# 案例007：全网变慢广播风暴（ARP 攻击）

【告警类型】BROADCAST_STORM
【来源】simulated（模拟工单，按常见故障模式编写）

## 工单现象
"网速突然很慢，一看交换机 CPU 特别高，广播包特别多"。整网访问延迟飙升，部分业务超时。

## 排查过程
1. `display cpu-usage`：接入交换机 CPU 达 90%+；
2. `display interface counters`：某接入端口广播帧占比异常（>60%）；
3. `display mac-address`：同一 MAC 出现在多个端口，且存在大量未知单播；
4. 定位到中毒终端网卡不断发送伪造 ARP 广播；断开该端口后广播风暴消失。

## 根因
终端中毒后持续发送大量伪造 ARP 广播报文，形成广播风暴冲击交换机 CPU。

## 处置
隔离中毒端口；接入层启用端口安全（MAC 绑定）与广播抑制（storm-control）。

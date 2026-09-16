# 案例001：办公区终端反复断网（端口抖动）

【告警类型】LINK_FLAPPING
【来源】simulated（模拟工单，按常见故障模式编写）

## 工单现象
用户报"网断了好几次，换什么都说不是他们的问题"。该楼层终端间歇性掉线，ping 网关时通时断，网络时好时坏。

## 排查过程
1. `display interface GigabitEthernet0/0/1`：接口状态在 up/down 之间反复切换，日志出现大量 Link flap；
2. `display interface brief`：确认仅该接入端口抖动，同设备其他端口正常；
3. `display transceiver interface GigabitEthernet0/0/1`：收发光功率正常，排除光模块；
4. 现场检查：网线水晶头氧化、插接松动，重新压接后问题消失。

## 根因
物理层链路接触不良（网线水晶头氧化/松动）导致端口频繁 flapping，进而造成终端断网重连。

## 处置
重新压接水晶头并固定网线；端口配置 error-down 自动恢复 + 日志告警，便于下次快速定位。

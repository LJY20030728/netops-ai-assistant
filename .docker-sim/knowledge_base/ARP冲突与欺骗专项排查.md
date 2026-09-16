# ARP 冲突与欺骗专项排查

## 问题现象
主机间歇性无法访问网关或互访，物理链路与接口状态均正常；同一 IP 在不同时间被不同 MAC 应答，或交换机 ARP 表项频繁刷新/变化。

## 排查步骤
1. 查看交换机 ARP 表与变化：
   ```
   display arp
   display arp all
   ```
   - 对比目标 IP 的 MAC 是否与真实设备 MAC 一致；
   - 注意 Expire 时间是否过短（正常 3-20 分钟，异常时几秒就刷新）。

2. 查看 ARP 冲突日志：
   ```
   display logbuffer | include ARP
   ```
   - `ARP_CONFLICT` / `Duplicate address` 日志说明同一 IP 被两个 MAC 应答（冲突或欺骗）。

3. 定位真实 MAC：
   - 在交换机上查该 MAC 出现在哪个接口：`display mac-address <MAC>`；
   - 拔线法：逐个断开可疑端口，观察 ARP 表项与 ping 是否恢复。

4. 检查网关与静态 ARP：
   - 是否配置了静态 ARP 绑定（display arp static），被攻击者覆盖；
   - 终端是否安装了 ARP 防火墙/网关绑定工具。

5. 二层隔离与防护：
   - 端口安全（port-security）：限制单端口 MAC 数量；
   - DHCP Snooping + ARP 防欺骗（dynamic arp inspection）联动。

## 常见根因与处置
| 根因 | 处置 |
|---|---|
| 私接设备抢占 IP（IP 冲突） | 定位冲突 MAC 所在端口，移除违规设备 |
| ARP 欺骗攻击 | 开启 DHCP Snooping + ARP 检测，配置端口安全 |
| 静态 ARP 绑定被覆盖 | 删除错误绑定，重新下发正确的静态 ARP |
| 终端网关配置错误 | 核对终端 IP/网关/掩码，改为 DHCP 下发 |

## 注意事项
ARP 问题往往"时通时断"，排查时要同时看表项、日志、MAC 位置三个维度互相印证；不要只凭一次 ping 结果下结论。

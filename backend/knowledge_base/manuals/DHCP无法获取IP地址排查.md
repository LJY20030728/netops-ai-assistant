# DHCP 无法获取 IP 地址排查

## 问题现象
终端网卡显示"正在获取 IP"或自动获得 169.254.x.x（APIPA）地址，无法上网；部分终端能获取、部分不能。

## 排查步骤
1. 确认 DHCP 服务器与地址池：
   ```
   display ip pool
   display dhcp server statistics
   display current-configuration | include dhcp
   ```
   - 地址池是否还有空闲地址（Excluded/Used 是否占满）；
   - DHCP 服务是否开启、接口是否配置了 dhcp select global/interface。

2. 检查接口 DHCP 配置：
   ```
   display ip interface brief
   display dhcp status
   ```
   - 终端所在 VLAN 的三层接口（Vlanif）是否启用 DHCP 服务；
   - DHCP 报文是广播，跨 VLAN 需要 DHCP Relay 或接口位于同一广播域。

3. 抓包定位 DORA 过程：
   - 终端抓包：是否发出 DHCP Discover，是否收到 Offer/Ack；
   - 只收 Discover 不收 Ack = 服务器回包被阻断或地址冲突检测失败。

4. 检查地址冲突：
   ```
   display dhcp server expired
   display logbuffer | include DHCP
   ```
   - 地址池与静态 IP 冲突、租约未释放导致分配失败；
   - 终端被分配到其他网段地址 = 有非法 DHCP 服务器（私接路由）。

5. 检查中继（跨网段）：
   ```
   display dhcp relay statistics
   ```

## 常见根因与处置
| 根因 | 处置 |
|---|---|
| 地址池耗尽 | 扩充地址池或缩短租约 |
| 接口未启用 DHCP | 配置 dhcp select global/interface |
| 非法 DHCP 服务器 | 开启 DHCP Snooping，信任合法端口 |
| 跨网段无中继 | 配置 DHCP Relay 指向服务器 |
| 地址冲突 | 清理冲突项，改用保留地址 |

## 注意事项
DORA 四步（Discover/Offer/Request/Ack）走到哪一步断了，故障点就在哪一段：Discover 都没发先看终端，Offer 收不到看服务器/中继，Ack 收不到查冲突。

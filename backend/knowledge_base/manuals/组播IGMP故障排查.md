# 组播 IGMP 故障排查

## 问题现象
终端收不到组播流（如 IPTV/视频直播黑屏）、加入组播组后无流量、组播流量在交换机/路由器上没有被正确复制转发。

## 排查步骤
1. 检查终端加入组播组：
   - 终端是否发出 IGMP Report（抓包确认）；
   - 交换机接口是否收到 Report：`display igmp interface` / `display igmp group`。

2. 检查二层组播（IGMP Snooping）：
   ```
   display igmp-snooping group
   display igmp-snooping configuration
   ```
   - 交换机是否开启 IGMP Snooping；
   - 组播组表项里目标端口是否包含接收终端所在端口（未加 = 没学到 Report）；
   - 路由口（Router port）是否正确，组播源方向是否可达。

3. 检查三层组播（PIM）：
   ```
   display pim neighbor
   display pim routing-table
   ```
   - PIM 邻居是否建立、RP（汇聚点）是否可达（稀疏模式）；
   - 组播路由表（S,G）是否存在。

4. 检查上游与源：
   - 组播源是否在发送、源所在网段是否能到达 RP/接收者；
   - 上游接口是否配置了 pim sm / igmp。

5. 检查过滤策略：
   - IGMP 过滤（igmp filter）/PIM 边界策略是否误过滤。

## 常见根因与处置
| 根因 | 处置 |
|---|---|
| Snooping 未开启 | 交换机开启 igmp-snooping |
| Report 没学到 | 检查终端与二层链路、VLAN |
| PIM 邻居/RP 不可达 | 配置/修复 PIM 与 RP 可达性 |
| 组播源方向错误 | 核对 RP 与源注册方向 |
| 过滤策略误拦 | 检查 IGMP/PIM 过滤配置 |

## 注意事项
组播排障的检查顺序：终端有没有发 Report → 交换机有没有学到组 → 三层有没有 (S,G) 路由 → 源和 RP 通不通；组播"看不到流量"先从接收端往上游逐层查。

# 无线 AP 离线与漫游故障排查

## 问题现象
部分 AP 在 AC（无线控制器）上显示离线/异常；终端连不上 Wi-Fi、频繁掉线；跨楼层/跨 AC 漫游时 IP 不变但流量中断或认证重来。

## 排查步骤
1. 查看 AP 状态：
   ```
   display wlan ap all
   display wlan ap name <AP名>
   ```
   - 状态为 Fault/Offline 时看 Run state 与记录的原因；
   - 关注 AP 的隧道状态（CAPWAP 隧道建立是否成功）。

2. 检查 AP 到 AC 的隧道：
   - CAPWAP 使用 UDP 5246（控制）/5247（数据），确认中间网络放行；
   - AP 无法获取管理 IP（DHCP）或无法解析 AC 域名/IP 时隧道建立失败。

3. 检查 AP 供电与硬件：
   - PoE 供电不足导致 AP 反复重启（查看 AP 重启次数）；
   - 网线长度、PoE 预算是否足够。

4. 检查射频与漫游：
   ```
   display wlan radio all
   display wlan client all
   ```
   - 信道/功率规划不合理导致同频干扰、覆盖黑洞；
   - 漫游不成功：检查快速漫游（802.11r/k/v）配置、AC 间漫游组配置。

5. 查看日志与报文：
   ```
   display logbuffer | include WLAN|CAPWAP
   ```

## 常见根因与处置
| 根因 | 处置 |
|---|---|
| CAPWAP 隧道中断 | 放行 5246/5247，恢复 AP 管理网络 |
| AP 拿不到地址 | 检查 AP 管理 VLAN 的 DHCP |
| PoE 供电不足 | 更换高功率 PoE 交换机端口 |
| 射频干扰严重 | 重新规划信道/功率，开启 RRM 自动调优 |
| 漫游配置缺失 | 开启 802.11r/k/v 与 AC 间漫游 |

## 注意事项
无线排障分层推进：物理（供电/线缆）→ 管理面（CAPWAP/DHCP）→ 射频面（信道/功率）→ 漫游（认证/漫游组），逐层排除。

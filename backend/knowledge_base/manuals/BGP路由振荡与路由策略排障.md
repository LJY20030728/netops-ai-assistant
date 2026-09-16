# BGP 路由振荡与路由策略排障

## 问题现象
BGP 邻居状态在 Established 与 Active/Connect 之间频繁切换（会话振荡），或邻居稳定但路由条目反复消失/出现（路由振荡），业务路由不稳定。

## 排查步骤
1. 查看 BGP 邻居状态与变化历史：
   ```
   display bgp peer
   display bgp peer verbose
   ```
   - 关注 State（Established/Active/Idle）、Up 时间、Last down reason；
   - Last down reason 常见：ConnectRetry（TCP 建立失败）、Hold timer expired（对端无响应）、Administrative reset。

2. 确认底层连通性：
   ```
   ping -a <本地地址> <对端地址>
   display ip routing-table <对端地址>
   ```
   - BGP 用 TCP 179 端口，底层路由不通则一直 Active；
   - 注意 ebgp 默认 TTL=1，多跳需要配置 ebgp-max-hop。

3. 检查更新源与邻居配置：
   - ebgp 邻居的 update-source 是否指定了正确的源地址（未指定时用出接口地址，可能与对端期望不一致）；
   - AS 号、认证（MD5/Keychain）、Keepalive/Hold 定时器两端是否一致。

4. 检查路由策略（route-policy/filter-policy）：
   ```
   display bgp routing-table
   display current-configuration | include peer
   ```
   - 入向/出向 route-policy 过滤过严会把该收到的路由全部过滤掉；
   - 前缀列表（ip ip-prefix）顺序错误导致部分路由丢失。

5. 查看日志确认会话变更原因：
   ```
   display logbuffer | include BGP
   ```

## 常见根因与处置
| 根因 | 处置 |
|---|---|
| 底层链路/路由不稳定 | 先修 IGP（OSPF/静态），保证 TCP 可达 |
| ebgp 多跳未配 | 配置 peer ebgp-max-hop |
| 更新源地址不匹配 | 两端统一 update-source 与对端 peer 地址 |
| 定时器不一致 | 统一 keepalive/holdtime |
| 策略过滤过严 | 检查 route-policy/前缀列表，放行必要前缀 |
| 认证不匹配 | 核对 MD5/Keychain 口令 |

## 注意事项
排查顺序固定：先 TCP 可达性，再邻居参数，最后路由策略；每改一步观察邻居状态是否稳定再继续。

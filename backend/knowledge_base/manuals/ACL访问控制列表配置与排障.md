# ACL 访问控制列表配置与排障

## 问题现象
接口状态正常（up/up）但业务流量不通：ping 超时、业务端口拒绝访问，排查物理链路与路由均无异常时，需重点检查 ACL 过滤。

## 排查步骤
1. 查看接口上应用了哪些 ACL：
   ```
   display traffic-filter applied-record
   display this
   ```
   重点关注接口的 inbound / outbound 方向是否绑定了 ACL，以及绑定的是哪个编号。

2. 查看 ACL 具体规则与匹配计数：
   ```
   display acl 3001
   display acl all
   ```
   - `rule` 行末尾的 `(N times matched)` 是命中计数，若在增长说明流量正在被该规则处理；
   - 华为 ACL 按规则编号升序匹配，先匹配到先生效，隐含拒绝（deny）在末尾。

3. 确认规则顺序与方向：
   - 方向绑错（应在 inbound 绑成 outbound）会导致过滤失效或误伤；
   - 规则顺序错误：permit 写在 deny 之后会被先命中的 deny 挡住。

4. 检查隐含拒绝与未放行流量：
   - 高级 ACL（3000-3999）默认最后隐含 deny all；
   - 只 permit 了部分协议/网段，其他流量全部被隐含拒绝，业务看起来"莫名其妙不通"。

5. 查看日志确认丢弃行为：
   ```
   display logbuffer | include ACL
   ```

## 常见根因与处置
| 根因 | 处置 |
|---|---|
| 接口绑定了错误的 ACL/方向 | 检查 traffic-filter 绑定，修正接口与方向 |
| 规则顺序错误导致误拦 | 调整 rule 编号顺序，permit 前置 |
| 隐含拒绝放行不足 | 补充 permit 规则或改为白名单+显式放行 |
| 匹配计数暴涨 | 检查是否有攻击流量命中 deny 规则，结合安全策略处置 |
| ACL 未下发/未保存 | 确认配置已生效（display traffic-filter），并 save 保存 |

## 注意事项
ACL 是安全的第一道防线，修改前建议先备份当前配置；放行规则尽量精细化到源/目的 IP 与端口，避免大范围 permit。

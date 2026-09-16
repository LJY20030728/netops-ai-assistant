# SNMP 网管不通排查

## 问题现象
网管平台（NMS）无法发现设备、轮询不到指标、设备告警收不到；部分设备能纳管、部分不能；community/团体字或认证报错。

## 排查步骤
1. 验证 SNMP 服务状态：
   ```
   display snmp-agent sys-info
   display snmp-agent statistics
   ```
   - 确认 SNMP 服务已开启（v1/v2c/v3）；
   - 查看统计中的错误计数（bad community、bad version、parse error）。

2. 检查团体字/用户名：
   - v2c：NMS 与设备的 read/write community 必须一致；
   - v3：用户、认证算法（MD5/SHA）、加密算法（DES/AES）、上下文必须一致。

3. 检查网络可达性：
   - NMS 到设备管理地址 ping 通、UDP 161 端口可达；
   - 中间防火墙/ACL 是否放行 UDP 161（trap 用 UDP 162 发往 NMS）。

4. 检查 ACL 限制：
   ```
   display snmp-agent acl
   ```
   - SNMP 绑定了 ACL 时，只允许 ACL 内的 NMS 访问；NMS 地址不在内会收不到响应。

5. 检查 Trap 配置：
   - trap 目标地址（NMS IP）配置是否正确；
   - trap 使能范围（inform 与 trap 的区别）。

## 常见根因与处置
| 根因 | 处置 |
|---|---|
| 团体字/认证不一致 | 统一 v2c community 或 v3 认证参数 |
| UDP 161/162 被拦 | 放行网管流量 |
| SNMP ACL 限制 | 将 NMS 地址加入允许列表 |
| 服务未开启 | snmp-agent 使能并配置版本 |
| Trap 目标错误 | 修正 trap-host 指向 NMS |

## 注意事项
SNMP 排障先看设备侧统计（有没有收到请求/报什么错），再看网络放行，最后核对认证参数；v3 的认证加密参数最容易配错。

# QinQ 与二层透传配置

## 问题现象
运营商/城域网透传场景下客户 VLAN 冲突（多个客户使用相同 VLAN ID）、二层报文无法正确透传、双 Tag 报文在交换机上异常。

## 排查步骤
1. 确认 QinQ 需求：
   - 客户侧 VLAN（内层 Tag）与运营商侧 VLAN（外层 Tag）冲突时使用 QinQ 双 Tag 封装；
   - 确认接口模式（QinQ 只能在 Trunk/Hybrid 上配置）。

2. 查看 QinQ 配置：
   ```
   display qinq configuration
   display interface <端口> | include QinQ
   ```
   - 接口是否配置了 qinq vlan-translation / dot1q termination；
   - 外层 Tag（S-VLAN）分配是否正确，是否与客户内层 Tag 冲突。

3. 检查 VLAN 透传路径：
   - 中间设备（二层交换机）是否放行外层 S-VLAN；
   - 透传设备（不做 QinQ 的设备）Trunk 是否允许 S-VLAN 通过。

4. 检查终结（解封装）侧：
   - 对端/业务侧是否正确终结 QinQ（dot1q termination vid 外层）；
   - 终结后内层 VLAN 是否被正确剥离/识别。

5. 验证报文：
   - 抓包确认双 Tag（外层+内层）是否正确；
   - 查看接口收发计数是否有增量。

## 常见根因与处置
| 根因 | 处置 |
|---|---|
| 外层 VLAN 冲突 | 统一规划 S-VLAN 分配 |
| 透传路径未放行 | Trunk 放行外层 VLAN |
| 终结配置错误 | 核对 dot1q termination 配置 |
| 接口模式不支持 | 改用 Trunk/Hybrid 并配置 QinQ |
| 报文异常 | 抓包确认双 Tag 结构 |

## 注意事项
QinQ 的排障关键是"内外层 Tag 分开看"：先确认封装端（加外层 Tag），再确认透传路径（放行外层），最后确认终结端（剥外层 Tag）；任何一端出错报文都到不了业务。

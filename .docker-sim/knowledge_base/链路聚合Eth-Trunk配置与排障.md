# 链路聚合 Eth-Trunk 配置与排障

## 问题现象
链路聚合后只有单条成员链路转发（负载不均衡）、成员端口频繁加入/退出、聚合组不 up，业务时通时断或带宽不叠加。

## 排查步骤
1. 查看聚合组状态：
   ```
   display eth-trunk 1
   display trunkmembership eth-trunk 1
   ```
   - 成员端口是否都在 Selected 状态；Unselected 的端口不参与转发；
   - Selected 数量决定聚合带宽，只有 1 个 Selected 说明聚合失败。

2. 检查成员端口配置一致性：
   - 两端成员端口必须都在同一个聚合组、相同的速率/双工；
   - 成员端口必须是 Access/Trunk/Hybrid 模式一致；
   - 华为要求成员端口先加入 Eth-Trunk 再配置业务，或配置保持同步。

3. 检查对端聚合配置：
   - 对端也要配置相同编号的 Eth-Trunk；
   - 手工模式与 LACP 模式必须两端一致。

4. 检查 LACP 协商（LACP 模式）：
   ```
   display lacp statistics
   display eth-trunk 1 verbose
   ```
   - System ID、优先级、超时时间不一致会导致协商失败；
   - 看 LACP 状态机是否到达 Selected。

5. 验证负载分担：
   ```
   display load-balance
   ```
   - 默认按源/目的 MAC 或 IP 哈希，小流量/单流场景可能集中在一条链路（正常现象）。

## 常见根因与处置
| 根因 | 处置 |
|---|---|
| 成员端口配置不一致 | 统一成员端口属性后再加入聚合 |
| 对端聚合编号/模式不匹配 | 两端统一编号与模式 |
| LACP 协商失败 | 检查系统优先级、超时、对端配置 |
| 端口被 STP 阻塞 | 检查 STP 对成员端口的角色 |
| 单流负载不均 | 调整负载分担模式（IP 或 MAC 哈希） |

## 注意事项
聚合的黄金法则：两端配置必须镜像一致（编号/模式/成员属性）；查状态时先看 Selected 数量，再看未选中原因。

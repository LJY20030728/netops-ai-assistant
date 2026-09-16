# VLAN 与 Trunk 配置与排障

## 基本概念
- **Access 端口**：属于单个 VLAN，用于连接终端/服务器。
- **Trunk 端口**：透传多个 VLAN，用于交换机间或交换机到路由器/防火墙的级联。
- **Native VLAN**：Trunk 上不打标签的 VLAN，默认 VLAN 1。

## 常用命令

```
show vlan brief                     # 查看 VLAN 与端口成员
show interfaces trunk               # 查看 Trunk 及允许的 VLAN
show interfaces <端口号> switchport
show mac address-table              # 查看 MAC 学习情况
```

## 常见故障与排查

1. **终端无法通信**
   - 确认终端所在端口 Access VLAN 正确；
   - 确认 VLAN 在全局创建（`show vlan brief`）；
   - 确认对端交换机相应端口也在同一 VLAN / Trunk。

2. **跨交换机 VLAN 不通**
   - 级联口是否配成 Trunk；
   - Trunk 是否允许了目标 VLAN（allowed vlan 列表）；
   - 两端 Native VLAN 是否一致；
   - Trunk 封装协议（802.1Q）两端一致。

3. **Trunk 口显示 down / 协商失败**
   - 检查物理链路（光衰、双工速率协商）；
   - 检查 DTP 协商（建议两端显式配置 trunk）。

4. **VLAN 间路由不通**
   - 三层网关（SVI / 子接口）是否创建；
   - SVI 是否 shutdown 或没有 up（需至少一个 up 的 access 口在同一 VLAN）。

## 处置建议
- 以 `show vlan brief` + `show interfaces trunk` 交叉核对链路两端。
- 用 ping + MAC 表逐步定位二层可达性。
- 变更前备份配置，遵循变更窗口。

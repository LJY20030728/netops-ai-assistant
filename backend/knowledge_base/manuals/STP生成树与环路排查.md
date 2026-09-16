# STP 生成树与二层环路排查

【故障关键词】STP、生成树、二层环路、TCN、拓扑变更、Topology changes 暴涨


## 问题现象
广播风暴、CPU 飙升、MAC 表震荡、网络瘫痪，多为二层环路引起。

## 常用命令

```
show spanning-tree
show spanning-tree summary
show spanning-tree vlan <vlan-id>
show mac address-table
show logging | include STP|spanning
```

## 排查步骤

1. **确认是否存在环路**：
   - 观察 STP 端口角色/状态：Root / Designated / Alternate / Backup；
   - 正常链路中某条链路的端口应为 Alternate/Blocking；若全部 Forwarding，可能环路未被阻断。

2. **定位根桥与阻塞点**：
   - `show spanning-tree` 查看根桥、根端口、阻塞端口；
   - 若根桥意外漂移（如新接入的低优先级设备），会引发拓扑震荡。

3. **拓扑变更（TC）风暴排查**：
   - `show spanning-tree summary` 查看 Topology Changes 计数；
   - 频繁 TC 会导致全网 MAC 表反复刷新，业务抖动；
   - 定位触发 TC 的端口，多为端口频繁 up/down 或终端频繁上下线。

4. **检查 PortFast**：
   - 连接终端/服务器的端口应开启 PortFast（`spanning-tree portfast`），否则每次上线都要经历 30s 收敛；
   - 但 Trunk/交换机互联口禁止开 PortFast。

## 常见根因与处置
| 根因 | 处置 |
|---|---|
| 未做冗余链路阻断（STP 未生效） | 检查 STP 启用状态，确认阻塞点 |
| 根桥漂移 | 规划根桥优先级，核心设备设低值 |
| TC 风暴 | 定位触发端口，收敛/隔离 |
| 终端端口无 PortFast | 对接入端口配置 PortFast |
| 攻击（STP BPDU 攻击） | 开启 BPDU Guard / Root Guard |

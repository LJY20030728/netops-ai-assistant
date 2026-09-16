# ARP 与二层通信故障排查

## 问题现象
终端 IP 能 ping 通网关（三层通），但访问同一网段其他主机不通；或反向也不通。多与 ARP 学习异常有关。

## 常用命令

```
show arp
show ip arp
show mac address-table | include <目标MAC>
clear arp-cache        # 谨慎，会引发短暂中断
debug arp              # 谨慎使用
```

## 排查步骤

1. **ARP 表是否有目标条目**：`show arp` 看目标 IP 是否解析到 MAC。
   - 有 ARP 条目但不通 → 二层 MAC 转发问题，查 MAC 表与 VLAN。
   - 无 ARP 条目 → ARP 请求/应答未正常完成。

2. **确认目标主机在线**：目标主机防火墙（Windows 默认禁 ping/禁 ARP 应答策略）可能导致无响应。

3. **MAC 表定位转发路径**：查目标 MAC 在哪个端口/哪个 VLAN 学习到；若在错误端口学习，多为环路或端口接入异常。

4. **VLAN 一致性**：两端是否同 VLAN；Trunk 是否放行该 VLAN。

5. **防 ARP 攻击措施干扰**：Dynamic ARP Inspection（DAI）、DHCP Snooping 是否误拦合法 ARP 报文。

6. **代理 ARP 与网关**：跨网段访问依赖网关；确认默认网关、路由、ACL。

## 常见根因
- ARP 表满或条目错误（clear 后重学习）；
- 目标主机防火墙拦截；
- MAC 表震荡（环路）导致转发错乱；
- DAI/Snooping 误判；
- 二层端口在错误 VLAN。

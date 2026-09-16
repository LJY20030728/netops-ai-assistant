# BGP 邻居与路由故障排查

## 邻居状态机
Idle → Connect → Active → OpenSent → OpenConfirm → Established。

- 长期 **Idle/Active**：TCP 不可达或更新源不匹配。
- 卡在 **OpenSent/OpenConfirm**：BGP 参数协商失败（AS 号、Hold time、认证、多跳）。
- 到 **Established** 后无路由：策略（route-map / filter-list）过滤。

## 常用命令

```
show bgp summary
show bgp neighbors <对端IP>
show bgp ipv4 unicast
show ip bgp
debug bgp updates   # 谨慎使用
```

## 关键排查项

1. **TCP 可达性**：`ping` 对端更新源 IP；检查 ACL 是否放行 TCP 179。
2. **更新源**：eBGP 默认用直连接口地址作为源，`neighbor ... update-source loopback0` 用于 iBGP/多跳。
3. **多跳**：eBGP 跨跳时需 `ebgp-multihop`；TTL 检查默认 1。
4. **AS 号与认证**：两端 AS 配置正确，MD5/TCP-AO 口令一致。
5. **Hold time 不匹配**：协商取较小值；差距过大可能建不起来。
6. **路由策略**：network 声明、redistribute、route-map、前缀列表是否允许目标前缀。
7. **下一跳可达**：收到的路由若 next-hop 不可达则不会进入路由表。

## 处置
- 从 TCP 层 → BGP 会话层 → 路由策略层逐层排查。
- 用 `show bgp neighbors X received-routes` 与 `advertised-routes` 对比收发。
- 确认对端 AS 号正确（误配对端 AS 是常见建不起来的原因）。

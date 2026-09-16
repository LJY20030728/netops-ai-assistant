# BGP-Route-Reflector排障

## 症状
RR 环境客户端收不到其他客户端路由。

## 排查
- `display bgp peer` —— 看 reflector-client 标志
- `RR 只反射` —— 非 client 不自动传
- `cluster-list 防环` —— 被丢则检查

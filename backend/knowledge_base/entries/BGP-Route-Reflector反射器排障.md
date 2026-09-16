# BGP-Route-Reflector反射器排障

## 症状
RR 环境下客户端收不到其他客户端的路由。

## 排查
- `display bgp peer` —— 看 reflector-client 标志
- `RR 只反射不转发` —— 非 client 间路由不自动传
- `cluster-list 防环` —— 看是否被 cluster-list 丢弃

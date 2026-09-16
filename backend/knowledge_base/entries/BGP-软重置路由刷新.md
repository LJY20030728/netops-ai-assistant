# BGP-软重置路由刷新

## 症状
改 route-policy 后不生效。

## 排查
- `refresh bgp all` —— 软重置
- `reset bgp all` —— 硬重置断邻居

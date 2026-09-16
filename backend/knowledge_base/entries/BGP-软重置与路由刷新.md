# BGP-软重置与路由刷新

## 症状
改了 route-policy 但新策略不生效。

## 排查
- `refresh bgp all` —— 软重置不清邻居
- `reset bgp all` —— 硬重置会断邻居
- `cisco 用 clear ip bgp * soft` —— 等价

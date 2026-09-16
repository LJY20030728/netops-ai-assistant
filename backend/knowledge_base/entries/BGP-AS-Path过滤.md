# BGP-AS-Path过滤

## 症状
阻止特定 AS 路由。

## 排查
- `display routing-table protocol bgp` —— 看属性
- `as-path-filter 正则` —— ^_100_$
- `local-pref 优先级` —— 先于 prefs

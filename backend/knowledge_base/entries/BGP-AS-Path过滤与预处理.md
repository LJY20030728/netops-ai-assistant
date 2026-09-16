# BGP-AS-Path过滤与预处理

## 症状
需要阻止特定 AS 的路由，但 local-preference 不生效。

## 排查
- `display ip routing-table protocol bgp` —— 看路由属性
- `as-path-filter 正则` —— ^_100_$ 精确匹配
- `prefer 与 local-pref 优先级` —— local-pref 先于 prefs

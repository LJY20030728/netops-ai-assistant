# BGP-Community属性过滤

## 症状
按 community 过滤路由匹配不上。

## 排查
- `display route-policy` —— 看 if-match community
- `community-filter 团体列表` —— 需单独定义
- `send-community 必须配` —— 否则邻居收不到

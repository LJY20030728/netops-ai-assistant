# IPv6默认路由缺失

## 症状
IPv6 出不去。

## 排查
- `display ipv6 routing-table` —— 看 ::/0
- `RA 携带 prefix` —— 

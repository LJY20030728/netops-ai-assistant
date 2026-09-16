# BGP-Next-Hop-Self配置

## 症状
EBGP 引入到 IBGP 后对端 next-hop 不可达。

## 排查
- `peer x.x.x.x next-hop-local` —— IBGP 内改下一跳为自己
- `display bgp routing-table` —— 看 next-hop 是否可达

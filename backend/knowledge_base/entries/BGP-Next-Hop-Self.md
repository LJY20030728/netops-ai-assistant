# BGP-Next-Hop-Self

## 症状
IBGP 内 next-hop 不可达。

## 排查
- `peer next-hop-local` —— 改下一跳为自己
- `display bgp routing-table` —— 看 next-hop 可达

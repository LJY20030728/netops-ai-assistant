# BGP-路由黑洞

## 症状
BGP 通但业务断。

## 排查
- `display ip routing-table` —— 看路由
- `IBGP 未全连接` —— 路由消失
- `next-hop-local` —— 下一跳

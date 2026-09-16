# Route-Policy路由策略排障

## 典型症状
路由引入后某些路由没了；路由策略匹配但不生效；preference 修改后不生效。

## 原理速记
Route-Policy 节点 if-match 条件 apply 动作；节点间 or，节点内 and；引入顺序：先过滤再设置属性。

## 排查步骤
- `display route-policy NAME` —— 看节点号、if-match/apply 具体内容
- `display ip routing-table protocol ospf` —— 看引入后是否有期望路由
- `引入路由协议下 display this` —— 看是否调用了 route-policy

## 常见根因
节点号写反（大节点先匹配）；if-match ip-prefix 写错前缀；apply preference 与 import-route 顺序错。

## 处置与验证
期望路由出现/消失；属性（preference/community）按设计生效；不影响其他路由。

# OSPF-LSA类型详解与识别

## 症状
需要通过 LSA 类型判断网络结构或排查 LSA 泛洪问题。

## 排查
- `display ospf lsdb` —— 看 Type1/2/3/5 LSA
- `Type1 Router-LSA` —— 直连链路
- `Type3 Network-Summary` —— ABR 间网段
- `Type5 AS-External` —— 引入外部路由

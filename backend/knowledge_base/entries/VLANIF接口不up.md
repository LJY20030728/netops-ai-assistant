# VLANIF接口不up

## 症状
VLAN 已建但 VLANIF Down。

## 排查
- `display interface Vlanif10` —— 看状态
- `VLAN 内需活跃端口` —— 无成员口不 Up
- `display port vlan` —— 看成员

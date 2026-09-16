# MUX-VLAN隔离配置

## 症状
主从 VLAN 隔离后从端口不能互访。

## 排查
- `display mux-vlan` —— 看主从关系
- `separate 互访` —— group 互通
- `端口先加入主VLAN` —— 顺序不能反

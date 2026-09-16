# Hybrid端口VLAN排障

## 症状
Hybrid tagged/untagged 配置错。

## 排查
- `display port hybrid` —— 看列表
- `untagged 对应 PVID` —— 出方向剥标签
- `两端 PVID 一致` —— 否则打错标签

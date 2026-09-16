# Hybrid端口混合VLAN排障

## 症状
Hybrid 端口 tagged/untagged 配置错导致不通。

## 排查
- `display port hybrid` —— 看 tagged/untagged 列表
- `untagged 对应 PVID` —— 出方向剥标签
- `两端 PVID 需一致` —— 否则帧被打错标签

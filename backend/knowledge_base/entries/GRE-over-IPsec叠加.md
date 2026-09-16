# GRE-over-IPsec叠加

## 症状
先 GRE 后 IPsec。

## 排查
- `tunnel 模式` —— GRE
- `ipsec 保护 tunnel` —— 再加密
- 顺序错不工作

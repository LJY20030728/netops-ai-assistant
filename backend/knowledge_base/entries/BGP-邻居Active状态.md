# BGP-邻居Active状态

## 症状
BGP 卡 Active。

## 排查
- `display tcp status` —— 看 179 端口
- `acl 阻止 179` —— 检查
- `update-source loopback` —— 源接口

# DDoS与SYN Flood攻击防护排查

## 典型症状
服务器响应慢但接口利用率不高；连接表暴涨；半开连接占满。

## 原理速记
SYN Flood 利用三次握手未完成态耗尽服务器连接表；网络侧可配 TCP 代理（SYN Cookie/首包丢弃）。

## 排查步骤
- `display session statistics` —— 看半开连接比例
- `display firewall session table` —— 看会话数与新建速率
- `抓包看 SYN 标志位比例` —— 识别是否异常

## 常见根因
未开 SYN Cookie；连接表老化时间太长；攻击源被误判为合法。

## 处置与验证
开启 TCP 代理/首包丢弃；半开连接比例下降；服务器响应恢复。

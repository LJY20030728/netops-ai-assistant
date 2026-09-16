# NTP时间同步故障排查

## 典型症状
日志时间戳不一致导致跨设备故障关联错乱；NTP 客户端 stuck 在 unsynchronised。

## 原理速记
NTP 通过 stratum 层级同步；客户端依赖服务器可达 + 时间差在阈值内；认证密钥不匹配会静默拒绝。

## 排查步骤
- `display ntp status` —— 看 clock status 是否 synchronized、stratum
- `display ntp session` —— 看服务器可达、offset/delay
- `ping ntp服务器` —— UDP 123 可能被防火墙拦

## 常见根因
服务器地址错/不可达；认证密钥 mismatch；主时钟 stratum 过高。

## 处置与验证
状态 synchronized；全网络设备时间差 < 1s；日志时间戳可对齐关联。

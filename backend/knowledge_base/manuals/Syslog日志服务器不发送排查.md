# Syslog日志服务器不发送排查

## 典型症状
设备配置了日志服务器但采集器收不到日志；或只收部分级别。

## 原理速记
Syslog 用 UDP 514（或 TCP 1470）；需开启信息中心、配置主机、筛选级别；时间戳不对会丢上下文。

## 排查步骤
- `display info-center` —— 看信息中心是否 enable、channel 配置
- `display logbuffer` —— 看本地有没有日志生成（先确认源有日志）
- `ping log服务器` —— 测试 UDP 514 可达

## 常见根因
info-center source 未放通对应模块；级别设得太高（只发 critical）；时间戳未配 NTP。

## 处置与验证
采集器收到带正确时间戳的日志；级别与设计一致；断链/配置变更事件均能上报。

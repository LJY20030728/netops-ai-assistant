# ACL时间段配置

## 症状
ACL 绑定时间段不生效。

## 排查
- `display time-range` —— 看是否激活
- `系统时间正确` —— NTP 未同步不命中
- `rule 引用 time-range` —— 关联

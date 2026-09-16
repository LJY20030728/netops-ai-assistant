# 设备内存高占用与Flash告警

## 典型症状
设备 free memory 持续下降到告警阈值；Flash 空间不足无法保存配置。

## 原理速记
内存用于路由表/会话表/缓存；内存泄漏型上涨多为某协议邻居振荡；Flash 不足会导致 save 失败。

## 排查步骤
- `display memory` —— 看使用率、分配器统计
- `display memory-usage` —— 看各功能块占用，定位是路由表还是会话表
- `display flash:` —— 看剩余空间；清旧日志/core 文件

## 常见根因
BGP/OSPF 路由振荡导致重算风暴；日志级别太低刷爆内存；Flash 被老 core 文件占满。

## 处置与验证
内存回落；Flash 清理后剩余 > 20%；save 成功；振荡根源已修。

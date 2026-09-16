# 案例026：监控平台看不到设备（SNMP 不可达）

【告警类型】SNMP_UNREACHABLE
【来源】simulated（模拟工单，按常见故障模式编写）

## 工单现象
"监控平台突然看不到那台交换机了，snmp 不通，但设备还能管理"。某核心交换机从监控平台失联，但 SSH 登录设备正常。

## 排查过程
1. `display snmp-agent sys-info`：SNMP 服务运行正常；
2. `display snmp-agent community`：read community 与监控平台配置不一致（近期改密未同步监控侧）；
3. 从监控平台 `snmpwalk` 测试：认证失败（community 不匹配）；
4. 同步 community 配置后，监控恢复。

## 根因
设备侧 SNMP community 变更后未同步监控平台，认证失败导致设备从监控失联（管理通道不受影响）。

## 处置
统一社区字串变更流程（设备侧与监控侧同步执行）；SNMP 可达性纳入监控自愈检查。

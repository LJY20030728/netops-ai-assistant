# OSPF 邻居建立与故障排查

## 邻居状态机
Down → Init → 2-Way → ExStart → Exchange → Loading → Full。

停留在不同状态对应不同问题：
- 卡在 **Init**：收到对端 Hello 但对方没收到自己的；多为 MTU、认证、网络类型不匹配。
- 卡在 **2-Way**：正常（广播网络中仅 DR/BDR 继续建立 Full）。
- 卡在 **ExStart/Exchange**：MTU 不匹配或接口双工/速率问题。
- 卡在 **Loading**：LSA 交换异常，多为 MTU 或链路质量问题。

## 常用命令

```
show ip ospf neighbor
show ip ospf interface <接口>
show ip ospf
show ip ospf database
debug ip ospf adj   # 谨慎使用，生产需评估
```

## 关键排查项

1. **区域与进程**：两端 OSPF 进程、区域 ID 必须一致（ABR/骨干区域划分）。
2. **网络类型**：point-to-point / broadcast 需匹配；帧中继等 NBMA 场景需手动指定邻居。
3. **Hello/Dead 计时器**：两端必须一致（默认 Hello 10s / Dead 40s）。
4. **认证**：区域/接口认证类型与口令必须一致。
5. **MTU**：`ip ospf mtu-ignore` 可临时绕过 MTU 不一致问题，但应根治。
6. **接口状态**：接口必须 up、不是 passive、没有 ACL 阻断协议报文（组播 224.0.0.5/6）。
7. **Router ID**：两端 Router ID 不能冲突。

## 处置
- 逐项比对两端配置（区域、计时器、认证、网络类型、MTU）。
- 用 ping 大包（`ping size 1500 df-bit`）验证链路 MTU。
- 抓包确认 Hello 报文是否双向可达。

# GRE与L2TP隧道排障

## 典型症状
GRE 隧道 up 但内部协议邻居起不来；L2TP 用户拨不上。

## 原理速记
GRE 是 IP 封装 IP 的无状态隧道，依赖外层路由可达；L2TP 用 UDP 1701，需先建立控制连接再建会话。

## 排查步骤
- `display interface Tunnel0` —— 看隧道协议/物理 Up、源/目的地址
- `ping 目的外层地址` —— 先通外层 IP，再谈隧道内
- `display l2tp tunnel` —— 看隧道状态 Established、会话数

## 常见根因
外层路由不可达；GRE 与 IPSec 叠加顺序错；MTU 不匹配致大包分片丢。

## 处置与验证
Tunnel 协议 Up；隧道内能 ping 通；L2TP 会话建立并分配地址。

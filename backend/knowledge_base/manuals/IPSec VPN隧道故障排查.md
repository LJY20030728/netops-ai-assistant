# IPSec VPN隧道故障排查

## 典型症状
站点到站点 IPSec 隧道 ping 不通；IKE 阶段 1 或阶段 2 失败。

## 原理速记
IKEv2 先协商 IKE SA（阶段1：DH/加密/认证），再协商 IPsec SA（阶段2：感兴趣流/ESP）；两端策略必须镜像。

## 排查步骤
- `display ike sa` —— 看阶段1：状态 READY
- `display ipsec sa` —— 看阶段2：SPI、加密/认证算法
- `display acl 3000` —— 看感兴趣流（proxy ACL）是否镜像对称

## 常见根因
两端 IKE 策略优先级/算法不匹配；感兴趣流不对称；NAT 穿越未开导致 UDP 500 被拦。

## 处置与验证
IKE SA 与 IPsec SA 均建立；隧道下 ping 对端内网通；SA 有正常流量计数。

# VXLAN与EVPN排障

## 典型症状
数据中心 Overlay 跨 Leaf 虚拟机互访不通；EVPN 路由学习不到；BGP EVPN 邻居 Established 但 MAC 漂移。

## 原理速记
VXLAN 用 UDP 4789 封装，VTEP 隧道承载二层帧；EVPN 通过 MP-BGP 类型 2/5 路由发布 MAC/IP。

## 排查步骤
- `display interface Nve1` —— 看 VTEP 状态、源地址、VNI 绑定
- `display bgp evpn peer` —— 看 EVPN 邻居 Established；type2 路由是否收到
- `display mac-address vsi` —— 看远端 MAC 是否学习到、出接口对应隧道

## 常见根因
Underlay 路由不通致 VTEP 隧道建不起来；VNI/VSI 绑定错；BGP EVPN 地址族未使能。

## 处置与验证
先通 Underlay（VTEP 间 ping 通）；检查 VNI 映射；EVPN 邻居 Established 且 MAC 远端可见。

# MPLS基础与LDP邻居排障

## 典型症状
MPLS VPN 站点互访不通；LDP 邻居卡在 Init/OpenSent；标签分配失败导致业务走不通。

## 原理速记
MPLS 由 LDP 分发标签，PHP（倒数跳弹出）优化；PE 之间需 IGP 路由可达且标签栈正确压入。

## 排查步骤
- `display mpls ldp peer` —— 看邻居状态是否 Operational；非 Op 看 transport address 可达
- `display ip routing-table transport-address` —— LDP 用 loopback 建邻，需 IGP 学到对端 loopback
- `display mpls lsp` —— 看 LSP 状态 Up；标签收发方向

## 常见根因
transport address（loopback）未宣告进 IGP；接口未使能 mpls mpls ldp；ACL 阻止 TCP 646。

## 处置与验证
确保 loopback 进 OSPF；接口下 mpls 与 mpls ldp enable；邻居 Op 后 LSP Up，VPN 业务通。

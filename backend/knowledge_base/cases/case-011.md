# 案例011：与运营商建 BGP 邻居失败（AS 号配置错误）

【告警类型】BGP_NEIGHBOR_DOWN
【来源】simulated（模拟工单，按常见故障模式编写）

## 工单现象
"跟运营商建 bgp 邻居，as 号填错了现在起不来"。新接入专线配置 eBGP 后邻居持续 Down。

## 排查过程
1. `display bgp peer`：邻居状态 Idle，Last error 为 BGP 报文错误；
2. `display bgp error`：出现 OPEN 报文错误计数；
3. 核对运营商提供的 AS 号：配置为 65001，实际应为 4134（运营商 AS）；OPEN 报文中的 AS 号不匹配被对端拒绝；
4. 修正本地 AS 号并 `reset bgp all` 后邻居建立成功。

## 根因
本地 BGP AS 号配置与运营商实际 AS 不一致，OPEN 报文协商失败导致邻居无法建立。

## 处置
以运营商书面参数核对 AS 号/邻居地址/认证再配置；保留 OPEN 报文抓包作为排障证据。

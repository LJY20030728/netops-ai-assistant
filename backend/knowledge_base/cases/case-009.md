# 案例009：OSPF 邻居起不来（hello/dead 定时器不匹配）

【告警类型】OSPF_NEIGHBOR_DOWN
【来源】simulated（模拟工单，按常见故障模式编写）

## 工单现象
"ospf peer down，hello dead 不匹配"。互联链路物理正常（ping 通），但 OSPF 邻居始终无法建立。

## 排查过程
1. `display ospf peer`：邻居状态一直 Down，无进展；
2. `display ospf error`：出现 Hello 报文相关错误计数；
3. 对比两端 `display ospf interface`：一端 hello=10s/dead=40s，另一端被误配为 hello=30s/dead=120s；
4. 统一两端 hello/dead 定时器后邻居自动建立（OSPF 的 hello 定时器不一致会导致邻居无法协商）。

## 根因
OSPF 邻居两端 hello/dead 定时器不一致，Hello 报文互不认可，邻居建立失败。

## 处置
统一互联接口 OSPF 定时器；变更时以两端配置核对单校验 hello/dead 参数。

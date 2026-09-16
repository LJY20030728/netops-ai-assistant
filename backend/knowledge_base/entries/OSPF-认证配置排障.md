# OSPF-认证配置排障

## 症状
配置 OSPF 认证后邻居全 Down。

## 排查
- `display ospf interface` —— 看认证方式
- `两端密码模式一致` —— 明文 vs MD5 不兼容

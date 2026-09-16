# AAA认证RADIUS与TACACS排障

## 典型症状
设备登录时 RADIUS 超时走本地 fallback；TACACS+ 授权失败但认证成功。

## 原理速记
AAA 分认证（RADIUS 1812）与授权（TACACS+ 49）两步；需先配认证方案再授权方案；不可达按配置 fallback。

## 排查步骤
- `display radius-server configuration` —— 看服务器、共享密钥、端口
- `test-aaa user xxx password yyy` —— 模拟一次认证，看返回码
- `display aaa online-user` —— 看在线用户，确认走了哪个方案

## 常见根因
共享密钥两端不一致（常见！）；UDP 1812/1813 被拦；认证列表与域绑定未生效。

## 处置与验证
test-aaa 成功；登录日志显示 RADIUS 认证通过；fallback 路径符合设计预期。

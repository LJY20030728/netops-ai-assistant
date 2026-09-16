# NAT 地址转换配置与排障

## 问题现象
内网可以访问外网但外网无法访问内网服务；或部分应用（FTP/VoIP/视频）打不开；NAT 表项异常、转换后丢包。

## 排查步骤
1. 查看 NAT 表项：
   ```
   display nat session all
   display nat address-group
   ```
   - 确认内网源地址是否成功转换、转换后的公网地址池是否正确；
   - 表项不存在 = 流量没命中 NAT 策略。

2. 检查 NAT 策略匹配：
   ```
   display nat policy
   display current-configuration | include nat
   ```
   - 源/目的地址范围、出接口是否匹配实际流量；
   - 策略顺序：先匹配先生效。

3. 检查地址池与端口：
   - 公网地址池耗尽（地址用光）会导致新会话无法建立；
   - PAT（端口复用）与一对一（NO-PAT）的配置区别影响并发能力。

4. 特殊协议处理：
   - FTP（被动模式）、SIP、H.323 等带内信令协议需要 ALG（应用层网关）配合；
   - NAT 后视频/语音单通时优先怀疑 ALG 未开启或版本不兼容。

5. 验证双向：
   ```
   display nat session table verbose
   ping -a <公网地址> <目的>
   ```
   - 外网访问内网服务器需要目的 NAT（server-map / nat server）。

## 常见根因与处置
| 根因 | 处置 |
|---|---|
| NAT 策略未命中 | 核对源/目的/出接口，修正策略 |
| 地址池耗尽 | 扩充地址池或改为 PAT 复用 |
| ALG 未开启 | 开启对应协议 ALG |
| 端口映射缺失 | 配置 nat server 映射内网服务 |
| 会话老化异常 | 调整 NAT 会话老化时间 |

## 注意事项
NAT 排障先看"流量有没有命中策略"（表项），再看"转换结果对不对"（地址/端口），最后看"特殊协议是否兼容"（ALG）。

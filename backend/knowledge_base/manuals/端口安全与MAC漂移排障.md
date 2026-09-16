# 端口安全与MAC漂移排障

## 典型症状
同一 MAC 在不同端口间漂移；端口安全 shutdown 后业务断；CAM 表不稳定。

## 原理速记
端口安全限制端口学习 MAC 数，超阈值即 shutdown；MAC 漂移多为私接小交换机/环路/双网卡。

## 排查步骤
- `display mac-address` —— 看 MAC 对应端口是否变化
- `display interface` —— 看端口是否被 error-down
- `display logbuffer` —— 看 MAC 漂移记录

## 常见根因
私接未管理的交换机；双网卡绑定跨端口；环路导致 MAC 学习抖动。

## 处置与验证
定位私接设备；端口安全策略放宽或整改；MAC 表稳定不再漂移。

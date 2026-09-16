# OSPF-虚链接配置排障

## 症状
跨非骨干区域用虚链接连通 Area 0。

## 排查
- `display ospf vlink` —— 看状态
- `transit area 须普通区域` —— Stub 不能做

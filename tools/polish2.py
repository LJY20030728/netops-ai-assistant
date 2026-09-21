"""Fix the two remaining replacements by line-range."""
from pathlib import Path
p = Path(r"C:\Users\Curry\Desktop\项目二\netops-assistant\docs\项目自述-从第一性原理到落地.md")
lines = p.read_text(encoding="utf-8").splitlines()

# 第175行起（0-indexed 174）：替换双通道那段
# 找 "真实运维怎么解决？"
for i, line in enumerate(lines):
    if line.startswith("真实运维怎么解决？"):
        # 替换从 i 到 "互相 fallback。"
        j = i
        while j < len(lines) and "互相 fallback" not in lines[j]:
            j += 1
        new_block = [
            "真实运维怎么解决？就像机房里的服务器要双路电源——主电源挂了，UPS 还能撑着让你关机。网络设备也一样：",
            "",
            "* **业务通道**：走正常业务网（SSH）—— 你平时办公走的那条路；",
            "* **带外通道**：走独立管理网（Console 口、ILO、docker exec）—— 那条专门留给管理员的“后门”，和业务流量物理隔离。",
            "",
            "我在代码里做成双通道：netmiko 走 SSH，docker exec 走带外，互相 fallback。业务通道断了，带外还能让你登进去把故障收回来。",
        ]
        lines = lines[:i] + new_block + lines[j+1:]
        break

# dry_run 那段
c = "\n".join(lines)
old = """我加了一个 `dry_run` 动作：


1. Agent 说要注入故障时，系统先返回 "将要执行什么命令、影响哪个接口、预计什么后果"；

2. 60 秒内必须有一次 `dry_run` 请求过这个组合；

3. 没预览过就直接 inject，**直接拒绝执行**。

这个逻辑写在 `fault_state.py` 里。它的核心思想很朴素：**让模型在动手前先说一遍要做什么，人确认过了再干。** 这就是主管审批流程的缩影。"""
new = """我加了一个 `dry_run` 动作，思路直接搬自医院手术室那张“手术安全核对表”—— 医生动刀前必须停下来念一遍：患者是谁、做什么手术、切哪一侧。少念一遍不准下刀：

1. Agent 说要注入故障时，系统先返回“将要执行什么命令、影响哪个接口、预计什么后果、逆操作是什么”；
2. 60 秒内必须有一次 `dry_run` 请求过这个组合；
3. 没预览过就直接 inject，**直接拒绝执行**。

这个逻辑写在 `fault_state.py` 里。核心思想很朴素：**让模型在动手前先说一遍要做什么，人确认过了再干。** 这就是主管审批流程的缩影——只不过主管是肉眼核对，我是代码层强校验。模型想跳过这一步？代码不让。"""
if old in c:
    c = c.replace(old, new)
    print("dry_run replaced")
else:
    print("dry_run NOT FOUND")

p.write_text(c, encoding="utf-8")
print("done")

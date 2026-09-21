from pathlib import Path
p = Path(r"C:\Users\Curry\Desktop\项目二\netops-assistant\docs\项目自述-从第一性原理到落地.md")
lines = p.read_text(encoding="utf-8").splitlines()
# 237行起（1-indexed），0-indexed = 236
start = 236
end = 247  # 到"缩影。"那行（0-indexed 246）
new_block = [
    "我加了一个 `dry_run` 动作，思路直接搬自医院手术室那张“手术安全核对表”—— 医生动刀前必须停下来念一遍：患者是谁、做什么手术、切哪一侧。少念一遍不准下刀：",
    "",
    "1. Agent 说要注入故障时，系统先返回“将要执行什么命令、影响哪个接口、预计什么后果、逆操作是什么”；",
    "2. 60 秒内必须有一次 `dry_run` 请求过这个组合；",
    "3. 没预览过就直接 inject，**直接拒绝执行**。",
    "",
    "这个逻辑写在 `fault_state.py` 里。核心思想很朴素：**让模型在动手前先说一遍要做什么，人确认过了再干。** 这就是主管审批流程的缩影——只不过主管是肉眼核对，我是代码层强校验。模型想跳过这一步？代码不让。",
]
lines = lines[:start] + new_block + lines[end:]
p.write_text("\n".join(lines), encoding="utf-8")
print("ok")

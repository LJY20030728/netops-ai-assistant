"""Fix md issues."""
from pathlib import Path
p = Path(r"C:\Users\Curry\Desktop\项目二\netops-assistant\docs\项目自述-从第一性原理到落地.md")
c = p.read_text(encoding="utf-8")

# 1. 开头引用块合并
c = c.replace(
"""> 这篇不是宣传稿，是复盘。我会写清楚这个东西是怎么来的、每一步为什么这么选、踩了什么坑、以及它
>
> **不是什么**
>
> 。""",
"""> 这篇不是宣传稿，是复盘。我会写清楚这个东西是怎么来的、每一步为什么这么选、踩了什么坑、以及它**不是什么**。""")

# 2. 第2节引用块重写
c = c.replace(
"""> **请求**
>
> ："frr2 和 frr1 之间的 OSPF 邻居为什么断了？要批割接吗？"
> **他做的**
>
> ：
> 登 frr2，敲 
>
> `show ip ospf neighbor`
>
> ，看邻居状态是不是 Full；
> 登 frr1，看接口是不是 up；
> ping 一下对端地址；
> 翻排障手册，"OSPF 邻居不建立" 的常见原因；
> 综合这些事实，判断能不能批。""",
"""> **请求**："frr2 和 frr1 之间的 OSPF 邻居为什么断了？要批割接吗？"
>
> **他做的**：登 frr2，敲 `show ip ospf neighbor` 看邻居状态是不是 Full；登 frr1 看接口是不是 up；ping 一下对端地址；翻排障手册里"OSPF 邻居不建立"的常见原因；综合这些事实，判断能不能批。""")

# 3. 清理代码块里的 HTML 实体和转义
c = c.replace("&#x20;", " ")
c = c.replace("\\.", ".")
c = c.replace("\\#", "#")
c = c.replace("\\_", "_")

# 4. 第144行代码块里的反斜杠
c = c.replace("\\# docker-compose.frr.yml", "# docker-compose.frr.yml")

p.write_text(c, encoding="utf-8")
print("fixed")

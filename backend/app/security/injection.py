"""提示词注入检测（启发式模式匹配）。

说明：启发式规则用于快速拦截常见注入；生产环境建议叠加 LLM 检测与更完整的
输入/工具输出双端校验。命中高风险模式直接阻断，中风险仅标记（由上层决定）。
"""
import re

# (正则, 严重级别)  high=阻断, medium=标记
_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions|prompts|messages|rules)", re.I), "high"),
    (re.compile(r"disregard\s+(previous|prior|above)\s+(instructions|prompts)", re.I), "high"),
    (re.compile(r"忽略(之前|以上|先前|前面).{0,12}(指令|指示|提示|要求|规则|内容)", re.I), "high"),
    (re.compile(r"忘了(之前|以上).{0,8}(指令|要求|设定)", re.I), "high"),
    (re.compile(r"(system|developer|assistant)\s*(prompt|instruction|message|prompt)", re.I), "high"),
    (re.compile(r"(系统提示词|系统指令|开发人员提示|角色设定)", re.I), "high"),
    (re.compile(r"你现在是|你是一个.{0,12}(助手|机器人|角色)|扮演.{0,10}角色", re.I), "medium"),
    (re.compile(r"(reveal|show|print|输出|泄露).{0,10}(system prompt|系统提示词|api[ _-]?key|密钥|token)", re.I), "high"),
    (re.compile(r"(base64|hex\s*decode|十六进制|URL\s*编码|rot13)", re.I), "medium"),
    (re.compile(r"这是.{0,6}命令.{0,12}(必须|请|要求)执行|按.{0,10}(执行|操作)", re.I), "medium"),
    (re.compile(r"如果不.{0,12}(惩罚|失败|扣分)|否则.{0,8}(惩罚|失败)", re.I), "medium"),
]


def scan_prompt_injection(text: str) -> list[dict]:
    """扫描文本，返回命中列表 [{pattern, severity}]。"""
    flags: list[dict] = []
    if not text:
        return flags
    for pat, sev in _PATTERNS:
        if pat.search(text):
            flags.append({"pattern": pat.pattern[:50], "severity": sev})
    return flags


def is_blocked(flags: list[dict]) -> bool:
    """是否命中高风险（需阻断）。"""
    return any(f["severity"] == "high" for f in flags)

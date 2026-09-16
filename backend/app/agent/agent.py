"""Agent 核心：手写 ReAct（Reasoning + Acting）循环。

流程：
1. 系统提示词向 LLM 描述可用工具与输出协议；
2. LLM 每步输出一个 JSON 决策：调用工具（{"action":"tool",...}）或结束（{"action":"finish"}）；
3. 工具结果作为 tool 消息回灌，继续循环直至 finish 或达到最大步数；
4. 最后用流式调用把"基于工具结果的最终回答"推给前端。

自研而非 LangGraph：无黑盒、依赖少、可完整讲解循环原理；
后续如需复杂图编排（条件分支/并行）可平滑迁移。
"""
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.config import settings
from app.agent.tools import TOOLS, execute_tool
from app.llm.zhipu_client import complete_json, stream_chat

MAX_STEPS = settings.agent_max_steps

# 工具列表文本（注入系统提示词）
_TOOLS_TEXT = "\n".join(
    f"- {t['name']}({', '.join(f'{k}={v}' for k, v in t['parameters'].items())}): {t['description']}"
    for t in TOOLS
)

AGENT_SYSTEM_PROMPT = f"""你是面向网络运维场景的 AI 助手「NetOps AI Assistant」，具备调用设备工具诊断故障的能力。

可用工具：
{_TOOLS_TEXT}

可用设备：core-sw-1（核心交换机）, core-rtr-1（核心路由器）, fw-1（防火墙）, frr1（FRR/OSPF）, frr2（FRR/OSPF+eBGP）, frr3（FRR/eBGP）
（frr1-3 为方案 B 真实 FRR 协议栈，仅 DEVICE_MODE=real 时可用；core-sw-1/core-rtr-1/fw-1 为仿真设备，仅仿真模式可用）
**重要（设备可用性规则）**：当前为 real 模式时，**只操作 frr1-3**，禁止尝试连接 core-sw-1/core-rtr-1/fw-1（仿真 SSH 服务未运行，连接必然失败）；frr 设备命令用 FRR 语法：show ip ospf neighbor / show bgp summary / show ip route / show interface eth0（display 系列为仿真设备语法，在 frr 设备上会被翻译，优先直接使用 FRR 语法）。

工作方式（ReAct）：
- 诊断类问题不要急于下结论：先收集足够证据（链路状态、协议邻居状态、连通性、知识库），再输出 finish；至少调用 2 个工具互相印证后再 finish；
- 排查连通性/协议问题时，建议按证据链推进：先 ping 测连通性 → 再 display interface brief / display interface <端口> 看链路状态与错误计数 → 再 display ospf peer brief / display bgp peer 看邻居状态 → 必要时 search_runbook 查排障步骤；
- **多设备交叉验证**：单点现象可能只在某台设备可见。若已在一台设备（如 core-sw-1）发现异常，建议到关联设备（core-rtr-1 / fw-1）交叉验证对端接口、协议邻居或 ARP 表，确认故障影响范围（例如交换机侧接口 up 不代表路由器侧正常）；
- **时序还原**：定位根因后，调用 get_event_timeline 获取故障事件时间线（最早→最新），在最终回答中给出「故障演进时间线」小节；
- **真实故障演练（frr1-3）**：仅当用户明确要求"在 FRR/真实环境上演练/注入故障"时才使用 frr_fault_inject；流程：先 action=status 记录基线 → action=inject 注入故障 → 取证确认故障现象 → 最后必须 action=recover 恢复并复验。**重要**：link_down 会切断该设备 SSH（业务=管理面），此时 run_device_command 会连接失败——SSH 失败本身就是故障症状，取证请改用 frr_fault_inject action=show（带外 docker exec，命令如 show ip ospf neighbor / show bgp summary）；
- 排障决策参考（通用网络知识，供选择工具时参考）：
  * 连通性异常：ping 确认丢包/超时 → display interface brief / display interface <端口> 看链路与错误计数 → display ospf peer / display bgp peer 看邻居状态 → display logbuffer 看日志 → display current-configuration 看配置；
  * 物理链路正常但不通：重点检查安全策略（display acl、display traffic-filter applied-record）、ARP（display arp）；
  * 时通时断/性能异常：display cpu-usage、display stp brief、display interface 统计（广播/错误/利用率）；
  * 协议邻居抖动：display logbuffer 看邻居变更原因、display <协议> peer 看状态与最近变化时间；
- **通用排障知识问题（未指定具体设备，例如"XX 不通应该检查什么/什么原因"）：不要直接调用设备命令，应先调用 search_runbook 检索排障手册取证，再 finish**；
- 一次只调用一个工具；拿到结果后分析，再决定下一个动作或 finish。

输出协议（严格 JSON，不要输出 JSON 以外的任何文字）：
1) 需要调用工具时：
{{"action":"tool","name":"工具名","arguments":{{"参数名":"值"}}}}
2) 信息已足够、可以回答时：
{{"action":"finish"}}

注意：
- 设备命令用华为命令；查看端口状态用 display interface brief 或 display interface <端口>；
- ping 丢包/不通时可用 tracert 定位断点；排障步骤可查 search_runbook；
- 一次只调用一个工具。"""

# 最终回答的系统提示词（流式生成）
FINAL_SYSTEM_PROMPT = """你是面向网络运维场景的 AI 助手「NetOps AI Assistant」。
下面是你（作为 Agent）针对用户问题调用工具得到的过程与输出。请基于这些真实的工具输出，撰写给用户的最终回答：
- 中文，结构清晰（可含步骤/列表/结论）；
- 引用关键数据（丢包率、端口状态、错误计数、OSPF 状态等）作为诊断依据，且只能引用工具输出中真实出现的数据；
- 若已通过 get_event_timeline 获取时间线，单独给出「故障演进时间线」小节（按时间先后列出关键事件）；
- 若证据来自多台设备，说明故障影响范围（哪些设备/接口受影响，对端是否正常）；
- 明确指出根因与处置建议。
【反幻觉硬约束】如果没有任何工具输出可依据，必须明确说明"未获取到设备数据，无法诊断"，严禁编造丢包率、端口状态、错误计数、命令输出等任何数据。"""


@dataclass
class _ToolCall:
    name: str
    arguments: dict


@dataclass
class _Finish:
    pass


# LLM 常见的"裸工具名 + JSON"拼接中的工具名 token（含别名）
_KNOWN_TOOL_NAMES = {
    "run_device_command", "ping", "traceroute", "search_runbook", "get_event_timeline",
    "frr_fault_inject", "frr_fault", "fault_inject", "inject_fault", "inject", "recover", "frr_lab",
    "display", "show", "tracert", "trace", "runbook", "search", "rag", "kb", "cli",
    "timeline", "event_timeline", "fault_timeline", "events",
}


def _obj_to_decision(obj) -> _ToolCall | _Finish | None:
    if not isinstance(obj, dict):
        return None
    action = obj.get("action")
    if action == "tool":
        name = str(obj.get("name", "")).strip()
        if not name:
            return None
        return _ToolCall(name, obj.get("arguments") or {})
    if action == "finish":
        return _Finish()
    return None


def _trailing_tool_name(head: str) -> str | None:
    """从 JSON 前的文字尾巴里提取裸工具名（如 '...run_device_command'）。"""
    toks = [t for t in re.split(r"[^a-zA-Z_]+", head) if t]
    if not toks:
        return None
    last = toks[-1].lower()
    return last if last in _KNOWN_TOOL_NAMES else None


def _parse_react(text: str) -> _ToolCall | _Finish | None:
    """解析 LLM 输出的决策。容忍 ```json 围栏、多余前后缀、'思考文字 + JSON' 拼接。"""
    if not text:
        return None
    cleaned = text.strip()
    # 去掉 markdown 代码围栏
    cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    # 尝试 1：整体就是 JSON
    try:
        return _obj_to_decision(json.loads(cleaned))
    except (json.JSONDecodeError, TypeError):
        pass
    # 尝试 2：提取大括号 JSON 片段；片段缺 name 时用片段前的裸工具名补上
    s, e = cleaned.find("{"), cleaned.rfind("}")
    if s != -1 and e != -1:
        head = cleaned[:s].strip()
        try:
            obj = json.loads(cleaned[s : e + 1])
        except (json.JSONDecodeError, TypeError):
            return None
        dec = _obj_to_decision(obj)
        if dec is not None:
            return dec
        # 片段无 action/name（如 {"device": ..., "command": ...}），用头部裸工具名补全
        tname = _trailing_tool_name(head)
        if tname and isinstance(obj, dict):
            return _ToolCall(tname, obj)
    return None


def _decision_messages(history: list[dict], message: str, tool_messages: list[dict]) -> list[dict]:
    msgs = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
    msgs += list(history)
    msgs.append({"role": "user", "content": message})
    msgs += tool_messages
    return msgs


def _final_messages(history: list[dict], message: str, tool_messages: list[dict]) -> list[dict]:
    msgs = [{"role": "system", "content": FINAL_SYSTEM_PROMPT}]
    msgs += list(history)
    msgs.append({"role": "user", "content": message})
    msgs += tool_messages
    msgs.append(
        {
            "role": "user",
            "content": "请基于以上工具输出，撰写最终回答。若未调用任何工具，请直接回答该问题。",
        }
    )
    return msgs


async def run_agent(message: str, history: list[dict], role: str = "operator") -> AsyncIterator[dict]:
    """运行 Agent，产出 SSE 事件：
    - {"type":"tool", "tool","args","result","ok"}  工具调用过程
    - {"type":"delta", "content"}                    最终回答流式文本
    - {"type":"done"}
    - {"type":"error", "message"}
    role：RBAC 角色，透传给工具层（viewer 不能调用设备工具）。
    """
    tool_messages: list[dict] = []
    steps = 0
    # 最近成功操作的设备：LLM 拼接格式常丢 device 参数，缺省时用上下文补上
    last_device: str | None = None
    # 强制取证：诊断类问题至少调用 3 个工具覆盖多证据维度（连通性/链路/协议或安全）再下结论。
    # 工具不足时模型输出 finish 会被拦截并要求继续取证；由 MAX_STEPS 兜底防死循环。
    MIN_TOOLS = 3
    retry_for_tools = 0
    MAX_RETRY = 4
    # 强制取证：诊断类问题至少调用 2 个工具收集互相印证的证据再下结论（防模型偷懒/幻觉）。
    # 工具不足 2 次时模型输出 finish 会被拦截并要求继续取证；由 MAX_STEPS 兜底防死循环。
    retry_for_tools = 0
    MAX_RETRY = 4

    def _tool_count() -> int:
        return sum(1 for m in tool_messages if m.get("role") == "tool")

    def _evidence_hint() -> str:
        """根据已调用工具给出下一步取证建议（通用网络排障逻辑，非预置答案）。"""
        contents = [m.get("content", "") for m in tool_messages if m.get("role") == "tool"]
        joined = "\n".join(contents)
        low = joined.lower()
        has_ping = any("ping" in n.lower() for n in [m.get("content", "") for m in tool_messages if m.get("role") == "tool"])
        checked_interface = "display interface" in low
        checked_acl = "display acl" in low or "traffic-filter" in low
        checked_arp = "display arp" in low
        has_timeline = "timeline" in low or "fault timeline" in low
        # 已涉及的设备集合（跨设备交叉验证提示）
        devs_seen: set[str] = set()
        for m in tool_messages:
            if m.get("role") != "assistant":
                continue
            content = str(m.get("content", ""))
            for dev in ("core-sw-1", "core-rtr-1", "fw-1"):
                if f'"{dev}"' in content or f"'{dev}'" in content:
                    devs_seen.add(dev)
        base = ""
        if has_ping and not checked_interface:
            base = (
                "请调用 run_device_command 查看链路维度：display interface brief（看 GE0/0/1 等接口 up/down 与错误计数），"
                "必要时 display interface <端口> 看详细统计与 display logbuffer 看日志。"
            )
        elif checked_interface and not (checked_acl or checked_arp):
            base = (
                "接口状态已确认。若接口 up 但 ping 丢包/超时，下一步必须检查安全策略与二层映射："
                "display acl、display traffic-filter applied-record（看接口是否应用 ACL 过滤）、display arp（看地址解析是否异常）。"
            )
        else:
            base = (
                "请调用 1 个互补维度工具互相印证：display logbuffer（看设备日志中的协议/安全事件）、"
                "display ospf peer / display bgp peer（看协议邻居）、或 search_runbook（检索排障手册）。"
            )
        # 跨设备交叉验证：已确认单点异常且只查了一台设备时提示
        if devs_seen and len(devs_seen) < 3:
            other = next(d for d in ("core-rtr-1", "fw-1", "core-sw-1") if d not in devs_seen)
            base += f"；为确认故障影响范围，建议到 {other} 交叉验证对端接口/协议邻居状态"
        # 时序还原：证据充足但还没取时间线时提示
        if _tool_count() >= 3 and not has_timeline and last_device:
            base += f"；如已定位根因，可调用 get_event_timeline(device='{last_device}') 还原故障演进时间线"
        return base

    try:
        while steps < MAX_STEPS:
            steps += 1
            decision_text = await complete_json(_decision_messages(history, message, tool_messages))
            parsed = _parse_react(decision_text)

            if parsed is None or isinstance(parsed, _Finish):
                if _tool_count() < MIN_TOOLS and retry_for_tools < MAX_RETRY:
                    retry_for_tools += 1
                    tool_messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"当前已调用 {_tool_count()} 个工具，证据不足以下结论。请继续调用诊断工具，不要直接 finish、不要输出文字。"
                                "必须严格输出如下格式（仅 JSON，不要任何其他文字）：\n"
                                '{"action":"tool","name":"run_device_command","arguments":{"device":"core-sw-1","command":"display logbuffer"}}\n'
                                "或 {\"action\":\"tool\",\"name\":\"ping\",\"arguments\":{\"device\":\"core-sw-1\",\"target\":\"10.0.1.2\"}}\n"
                                "下一步取证方向：" + _evidence_hint()
                            ),
                        }
                    )
                    continue
                break

            # 执行工具（缺 device 时用最近设备补上）
            tool_messages.append(
                {"role": "assistant", "content": f"调用工具 {parsed.name}，参数 {json.dumps(parsed.arguments, ensure_ascii=False)}"}
            )
            args = dict(parsed.arguments or {})
            if not args.get("device") and last_device:
                args["device"] = last_device
            try:
                result = await execute_tool(parsed.name, args, role=role)
                ok = True
                if parsed.name in ("run_device_command", "ping", "traceroute", "get_event_timeline") and args.get("device"):
                    last_device = args["device"]
            except Exception as exc:  # noqa: BLE001
                result = f"工具执行失败：{exc}"
                ok = False
            tool_messages.append({"role": "tool", "content": result})

            yield {
                "type": "tool",
                "tool": parsed.name,
                "args": parsed.arguments,
                "result": result[:600],
                "ok": ok,
            }

        # 流式输出最终回答
        async for chunk in stream_chat(_final_messages(history, message, tool_messages)):
            yield {"type": "delta", "content": chunk}
        yield {"type": "done"}
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": f"Agent 异常：{exc}"}

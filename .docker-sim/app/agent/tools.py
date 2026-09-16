"""Agent 工具注册表：定义工具元数据与执行函数。

Agent（LLM）只能调用这里注册的工具。新增工具 = 在 TOOLS 中注册元数据 + 实现 _execute。
"""
import json

from app.agent.devices import DeviceError, find_device, get_device_client, get_devices
from app.config import settings
from app.rag.retrieval import hybrid_retrieve

# 工具元数据（注入系统提示词，供 LLM 决策）
TOOLS = [
    {
        "name": "run_device_command",
        "description": "在指定网络设备上执行 CLI 命令（华为命令，如 display interface brief / display interface GigabitEthernet0/0/1 / display ospf peer brief / display version / display logbuffer / display current-configuration 等），返回设备原始输出。用于查看设备状态。",
        "parameters": {"device": "设备名，如 core-sw-1 / core-rtr-1 / fw-1", "command": "要执行的完整命令"},
    },
    {
        "name": "ping",
        "description": "从指定设备向目标地址发起 ping 测试，返回丢包率与往返时延，用于判断链路连通性与质量。",
        "parameters": {"device": "设备名，如 core-sw-1", "target": "目标 IP 或主机名，如 10.0.1.2", "count": "ping 次数，默认 4"},
    },
    {
        "name": "traceroute",
        "description": "从指定设备向目标地址发起 traceroute/tracert，追踪逐跳路径，用于定位链路断点或路由走向。",
        "parameters": {"device": "设备名", "target": "目标 IP 或主机名"},
    },
    {
        "name": "search_runbook",
        "description": "检索网络排障知识库（排障手册），返回与问题相关的排查步骤与处置建议。在回答排障类问题时配合使用。",
        "parameters": {"query": "检索关键词，如 '端口 flapping' / 'OSPF 邻居 down'"},
    },
]

_DEVICE_NAMES = ", ".join(d.name for d in get_devices()) or "（无设备）"


def _require_device(name: str):
    d = find_device(name)
    if d is None:
        raise DeviceError(f"设备 '{name}' 不存在。可用设备：{_DEVICE_NAMES}")
    return d


async def _run_device_command(args: dict) -> str:
    device = _require_device(args.get("device"))
    # 兼容不同参数键名（command/cmd/display/query/interface/port）
    command = ""
    for key in ("command", "cmd", "display", "query", "cli"):
        v = args.get(key)
        if v:
            command = str(v)
            break
    if not command:
        # 容错：arguments 里只有 interface/port 时组装 display interface 命令
        iface = args.get("interface") or args.get("port")
        if iface:
            command = f"display interface {iface}"
    command = command.strip()
    if not command:
        raise DeviceError("缺少 command 参数")
    client = get_device_client(device)
    out = await client.run(command)
    return f"设备 {device.name}（{device.role}）执行 '{command}' 输出：\n{out}"


async def _ping(args: dict) -> str:
    device = _require_device(args.get("device"))
    target = str(args.get("target", "")).strip()
    count = int(args.get("count") or 4)
    if not target:
        raise DeviceError("缺少 target 参数")
    client = get_device_client(device)
    out = await client.run(f"ping -c {count} {target}")
    return f"设备 {device.name} ping {target}（{count} 次）结果：\n{out}"


async def _traceroute(args: dict) -> str:
    device = _require_device(args.get("device"))
    target = str(args.get("target", "")).strip()
    if not target:
        raise DeviceError("缺少 target 参数")
    client = get_device_client(device)
    out = await client.run(f"tracert {target}")
    return f"设备 {device.name} tracert {target} 结果：\n{out}"


async def _search_runbook(args: dict) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        raise DeviceError("缺少 query 参数")
    hits = hybrid_retrieve(query, settings.rag_top_k)
    if not hits:
        return f"知识库中未检索到与 '{query}' 相关的内容。"
    sections = []
    for h in hits:
        src = h["metadata"].get("source", "未知")
        sections.append(f"[来源：{src}]\n{h['text']}")
    return "\n\n".join(sections)


_HANDLERS = {
    "run_device_command": _run_device_command,
    "ping": _ping,
    "traceroute": _traceroute,
    "search_runbook": _search_runbook,
}

# RBAC：各角色允许调用的工具
# viewer=只读问答（仅知识库检索）；operator=+只读设备工具；admin=全部
ROLE_TOOLS = {
    "viewer": ["search_runbook"],
    "operator": ["run_device_command", "ping", "traceroute", "search_runbook"],
    "admin": ["run_device_command", "ping", "traceroute", "search_runbook", "*"],
}


def tool_names() -> str:
    return ", ".join(t["name"] for t in TOOLS)


# 工具名容错：LLM 偶尔会把设备命令关键字当工具名，归一化到注册工具
_ALIASES = {
    "display": "run_device_command",
    "show": "run_device_command",
    "run": "run_device_command",
    "device_command": "run_device_command",
    "cli": "run_device_command",
    "exec": "run_device_command",
    "tracert": "traceroute",
    "trace": "traceroute",
    "runbook": "search_runbook",
    "search": "search_runbook",
    "rag": "search_runbook",
    "kb": "search_runbook",
}


def _normalize_name(name: str) -> str:
    return _ALIASES.get(name, name)


async def execute_tool(name: str, args: dict, role: str = "operator") -> str:
    """执行工具，返回结果文本。工具名未知/参数错误/越权会抛 DeviceError。"""
    name = _normalize_name(name)
    handler = _HANDLERS.get(name)
    if handler is None:
        raise DeviceError(f"未知工具：{name}。可用工具：{tool_names()}")

    allowed = ROLE_TOOLS.get(role, ROLE_TOOLS["viewer"])
    if name not in allowed and "*" not in allowed:
        raise DeviceError(f"当前角色（{role}）无权调用工具 {name}（仅允许：{', '.join(allowed) if '*' not in allowed else '全部'}）")

    return await handler(args or {})

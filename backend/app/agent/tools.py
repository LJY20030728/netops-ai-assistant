"""Agent 工具注册表：通过 @register_tool 装饰器自动收集。

新增工具 = 写一个 async 函数 + 加 @register_tool 装饰器，无需改 TOOLS/_HANDLERS。
"""
from app.agent.devices import DeviceError, find_device, get_device_client, get_devices
from app.agent.frr_lab import FrrLab, _LEGAL
from app.agent.registry import register_tool, registry
from app.config import settings
from app.rag.retrieval import hybrid_retrieve

_DEVICE_NAMES = ", ".join(d.name for d in get_devices()) or "（无设备）"


def _require_device(name: str):
    d = find_device(name)
    if d is None:
        raise DeviceError(f"设备 '{name}' 不存在。可用设备：{_DEVICE_NAMES}")
    return d


def _real_mode_device_guard(device) -> None:
    from app.config import settings
    if settings.device_mode == "real" and device.device_type != "frr":
        raise DeviceError(
            f"设备 {device.name} 是仿真设备，当前为 real 模式（仅 frr1-3 真实设备可用）；"
            "仿真设备需在 simulate 模式下使用"
        )


# shell 元字符 / 命令拼接特征：出现即拒绝（不依赖仿真器降级）
_SHELL_META = ("&&", "||", "|", ";", "`", "$(", "${", ">", "<", "\n", "\r", "\t&", " &")


def _guard_cli(value, what: str) -> str:
    """净化设备命令/目标参数：拒绝空值与 shell 元字符，防命令拼接注入。"""
    v = (value if isinstance(value, str) else str(value or "")).strip()
    if not v:
        raise DeviceError(f"缺少 {what} 参数")
    for bad in _SHELL_META:
        if bad in v:
            raise DeviceError(
                f"{what} 包含非法字符（{bad.strip() or repr(bad)}），已拒绝执行：不允许命令拼接"
            )
    return v


# ===== 工具注册 =====

@register_tool(
    name="run_device_command",
    description="在指定网络设备上执行 CLI 命令（华为命令，如 display interface brief / display ospf peer brief 等），返回设备原始输出。",
    parameters={"device": "设备名", "command": "要执行的完整命令"},
    roles=["operator", "admin"],
)
async def _run_device_command(args: dict) -> str:
    device = _require_device(args.get("device"))
    _real_mode_device_guard(device)
    command = ""
    for key in ("command", "cmd", "display", "query", "cli"):
        if args.get(key):
            command = str(args[key])
            break
    if not command:
        iface = args.get("interface") or args.get("port")
        if iface:
            command = f"display interface {iface}"
    command = _guard_cli(command, "command")
    client = get_device_client(device)
    out = await client.run(command)
    return f"设备 {device.name}（{device.role}）执行 '{command}' 输出：\n{out}"


@register_tool(
    name="ping",
    description="从指定设备向目标地址发起 ping 测试，返回丢包率与往返时延。",
    parameters={"device": "设备名", "target": "目标 IP", "count": "ping 次数，默认 4"},
    roles=["operator", "admin"],
)
async def _ping(args: dict) -> str:
    device = _require_device(args.get("device"))
    _real_mode_device_guard(device)
    target = _guard_cli(args.get("target"), "target")
    raw_count = args.get("count")
    if raw_count is not None:
        raw_count = _guard_cli(raw_count, "count")
        if not raw_count.isdigit() or int(raw_count) < 1 or int(raw_count) > 20:
            raise DeviceError("count 必须是 1-20 的整数")
    count = int(raw_count or 4)
    client = get_device_client(device)
    out = await client.run(f"ping -c {count} {target}")
    return f"设备 {device.name} ping {target}（{count} 次）结果：\n{out}"


@register_tool(
    name="traceroute",
    description="从指定设备向目标地址发起 traceroute，追踪逐跳路径。",
    parameters={"device": "设备名", "target": "目标 IP"},
    roles=["operator", "admin"],
)
async def _traceroute(args: dict) -> str:
    device = _require_device(args.get("device"))
    _real_mode_device_guard(device)
    target = _guard_cli(args.get("target"), "target")
    client = get_device_client(device)
    out = await client.run(f"tracert {target}")
    return f"设备 {device.name} tracert {target} 结果：\n{out}"


@register_tool(
    name="search_runbook",
    description="检索网络排障知识库（排障手册），返回相关排查步骤与处置建议。",
    parameters={"query": "检索关键词"},
    roles=["viewer", "operator", "admin"],
)
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


@register_tool(
    name="get_event_timeline",
    description="获取指定设备上的故障事件时间线（按时间升序还原故障演进）。",
    parameters={"device": "设备名"},
    roles=["operator", "admin"],
)
async def _get_event_timeline(args: dict) -> str:
    device = _require_device(args.get("device"))
    client = get_device_client(device)
    out = await client.run("display fault timeline")
    return f"设备 {device.name}（{device.role}）故障时间线：\n{out}"


@register_tool(
    name="frr_fault_inject",
    description="在 FRR 真实实验室注入/恢复/查看可逆故障。device=frr1/frr2/frr3；action=dry_run|inject|recover|status|show；fault=link_down|ospf_cost|bgp_neighbor_down；iface=eth0|eth1。inject 前必须先 dry_run 预览影响。",
    parameters={"device": "frr1/frr2/frr3", "action": "dry_run|inject|recover|status|show",
                "fault": "link_down|ospf_cost|bgp_neighbor_down", "iface": "eth0|eth1",
                "command": "action=show 时的只读 vtysh 命令"},
    roles=["admin"],
)
async def _frr_fault_inject(args: dict) -> str:
    from app.agent import fault_state
    device = _require_device(args.get("device"))
    action = str(args.get("action", "status")).strip().lower()
    fault = str(args.get("fault", "")).strip()
    iface = str(args.get("iface", "")).strip()
    lab = FrrLab(device)
    if action == "dry_run":
        if not fault or not iface:
            raise DeviceError("缺少 fault/iface 参数")
        out = lab.dry_run(fault, iface)
        fault_state.mark_dry_run(device.name, fault, iface)
        return out
    if action == "inject":
        if not fault or not iface:
            raise DeviceError("缺少 fault/iface 参数")
        if not fault_state.has_fresh_dry_run(device.name, fault, iface):
            raise DeviceError(
                f"安全拦截：inject {device.name} {fault} {iface} 前必须先 action=dry_run 预览影响（60 秒内有效）。"
                "请先调 action=dry_run，确认无影响后再 inject。"
            )
        result = await lab.inject(fault, iface)
        fault_state.mark_inject(device.name, fault, iface)
        return result
    if action == "recover":
        if not fault or not iface:
            recovered = []
            for f, i in _LEGAL.get(device.name, {}).items():
                try:
                    await lab.recover(f, i)
                    recovered.append(f"{f}:{i}")
                except Exception as exc:  # noqa: BLE001
                    recovered.append(f"{f}:{i} 失败:{exc}")
            fault_state.clear_recover(device.name)
            return f"[FRR:{device.name}] 已幂等恢复全部合法故障：{', '.join(recovered)}"
        result = await lab.recover(fault, iface)
        fault_state.clear_recover(device.name, fault)
        return result
    if action == "status":
        return await lab.status(fault or "link_down", iface or "eth0")
    if action == "show":
        command = _guard_cli(args.get("command"), "command")
        if not command.lower().startswith(("show ", "display ", "verify ")):
            raise DeviceError("action=show 仅允许只读命令")
        out = await lab._run(f'vtysh -c "{command}"')
        return f"[FRR:{device.name}] 带外执行 '{command}' 输出：\n{out}"
    raise DeviceError("action 必须为 dry_run/inject/recover/status/show")


# ===== 对外接口（保持兼容）=====

TOOLS = registry.metadata()

_ALIASES = {
    "display": "run_device_command", "show": "run_device_command", "run": "run_device_command",
    "device_command": "run_device_command", "cli": "run_device_command", "exec": "run_device_command",
    "tracert": "traceroute", "trace": "traceroute",
    "runbook": "search_runbook", "search": "search_runbook", "rag": "search_runbook", "kb": "search_runbook",
    "timeline": "get_event_timeline", "event_timeline": "get_event_timeline",
    "fault_timeline": "get_event_timeline", "events": "get_event_timeline",
    "frr_fault": "frr_fault_inject", "fault_inject": "frr_fault_inject",
    "inject_fault": "frr_fault_inject", "inject": "frr_fault_inject",
    "recover": "frr_fault_inject", "frr_lab": "frr_fault_inject",
}


def tool_names() -> str:
    return ", ".join(registry.names())


def _normalize_name(name: str) -> str:
    return _ALIASES.get(name, name)


async def execute_tool(name: str, args: dict, role: str = "operator") -> str:
    name = _normalize_name(name)
    handler = registry.handler(name)
    if handler is None:
        raise DeviceError(f"未知工具：{name}。可用工具：{tool_names()}")

    allowed = registry.roles(name)
    if role not in allowed:
        raise DeviceError(f"当前角色（{role}）无权调用工具 {name}（允许角色：{', '.join(allowed)}）")

    return await handler(args or {})

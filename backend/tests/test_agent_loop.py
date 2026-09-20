"""ReAct loop 真测试：mock LLM 决策序列，断言工具真的被调、结果真的回灌。"""
import asyncio
from unittest.mock import patch

from app.agent.agent import run_agent


def _run(coro):
    return asyncio.run(coro)


def test_agent_loop_executes_tool_and_feeds_back():
    """LLM 先调 run_device_command，第二次看到工具结果后 finish。"""
    script = [
        '{"action":"tool","name":"run_device_command","arguments":{"device":"core-sw-1","command":"display interface brief"}}',
        '{"action":"finish"}',
    ]
    calls = []

    async def fake_complete_json(messages):
        if len(calls) >= 1:
            tool_msgs = [m for m in messages if m.get("role") == "tool"]
            assert tool_msgs, "工具结果未回灌到 LLM 决策消息"
            assert "GE0/0/1" in str(tool_msgs), "工具输出内容未回灌"
        calls.append(messages)
        return script[min(len(calls) - 1, len(script) - 1)]

    async def fake_stream(*a, **kw):
        yield "诊断完成：GE0/0/1 up。"

    async def main():
        events = []
        with patch("app.agent.agent.complete_json", side_effect=fake_complete_json), \
             patch("app.agent.agent.stream_chat", fake_stream), \
             patch("app.agent.agent.execute_tool", return_value="GE0/0/1 up, errors=0") as mock_exec:
            async for ev in run_agent("接口状态如何", [], role="admin", session_id="test_loop_1"):
                events.append(ev)
        return events, mock_exec

    events, mock_exec = _run(main())

    assert mock_exec.called, "execute_tool 未被调用"
    name, args = mock_exec.call_args[0]
    assert name == "run_device_command"
    assert args["device"] == "core-sw-1"

    tool_events = [e for e in events if e.get("type") == "tool"]
    assert tool_events, "没有 tool 事件"
    assert tool_events[0]["ok"] is True
    assert any(e.get("type") == "done" for e in events), "没有 done 事件"


def test_agent_loop_hallucinated_tool_rejected():
    """LLM 编了不存在的工具名，loop 应拒绝并回灌可用工具清单，不执行。"""
    script = [
        '{"action":"tool","name":"nonexistent_tool","arguments":{}}',
        '{"action":"finish"}',
    ]
    calls = []

    async def fake_complete_json(messages):
        calls.append(messages)
        return script[min(len(calls) - 1, len(script) - 1)]

    async def fake_stream(*a, **kw):
        yield "ok"

    async def main():
        events = []
        with patch("app.agent.agent.complete_json", side_effect=fake_complete_json), \
             patch("app.agent.agent.stream_chat", fake_stream), \
             patch("app.agent.agent.execute_tool") as mock_exec:
            async for ev in run_agent("随便问", [], role="admin", session_id="test_loop_2"):
                events.append(ev)
        return events, mock_exec

    events, mock_exec = _run(main())

    assert not mock_exec.called, "不存在的工具竟被执行了"
    tool_events = [e for e in events if e.get("type") == "tool"]
    assert tool_events and tool_events[0]["ok"] is False
    assert any("可用工具" in str(m.get("content", "")) for m in calls[1]), "未回灌可用工具清单"


def test_agent_loop_hallucinated_device_rejected():
    """LLM 编了不存在的设备，loop 应拒绝并回灌可用设备清单。"""
    script = [
        '{"action":"tool","name":"run_device_command","arguments":{"device":"nonexistent-dev","command":"x"}}',
        '{"action":"finish"}',
    ]
    calls = []

    async def fake_complete_json(messages):
        calls.append(messages)
        return script[min(len(calls) - 1, len(script) - 1)]

    async def fake_stream(*a, **kw):
        yield "ok"

    async def main():
        events = []
        with patch("app.agent.agent.complete_json", side_effect=fake_complete_json), \
             patch("app.agent.agent.stream_chat", fake_stream), \
             patch("app.agent.agent.execute_tool") as mock_exec:
            async for ev in run_agent("随便问", [], role="admin", session_id="test_loop_3"):
                events.append(ev)
        return events, mock_exec

    events, mock_exec = _run(main())

    assert not mock_exec.called, "不存在的设备竟被操作了"
    assert any("可用设备" in str(m.get("content", "")) for m in calls[1]), "未回灌可用设备清单"

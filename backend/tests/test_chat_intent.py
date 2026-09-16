"""is_agent_intent 意图判定测试：纯函数，不依赖外部服务。"""
from app.routers.chat import is_agent_intent


def test_named_frr_device_triggers_agent():
    assert is_agent_intent("请在 frr1 上注入 ospf_cost 故障") is True
    assert is_agent_intent("查看 frr2 的邻居状态") is True


def test_named_legacy_device_triggers_agent():
    assert is_agent_intent("core-sw 端口 CRC 错误怎么排查") is True
    assert is_agent_intent("fw-1 策略路由检查") is True


def test_ip_address_triggers_agent():
    assert is_agent_intent("ping 192.168.1.1 通不通") is True
    assert is_agent_intent("tracert 10.0.0.1") is True


def test_network_target_with_action_triggers_agent():
    assert is_agent_intent("检查一下 OSPF 邻居状态") is True
    assert is_agent_intent("BGP 链路丢包严重请排查") is True


def test_pure_knowledge_question_does_not_trigger_agent():
    # 没有点名设备、没有 IP、没有明确动作+目标
    assert is_agent_intent("OSPF 和 BGP 的区别是什么") is False
    assert is_agent_intent("交换机和路由器的工作原理") is False


def test_short_greeting_does_not_trigger_agent():
    assert is_agent_intent("你好") is False
    assert is_agent_intent("谢谢") is False


def test_empty_or_whitespace():
    # 空字符串不应触发；无动作无目标
    assert is_agent_intent("") is False
    assert is_agent_intent("   ") is False

# -*- coding: utf-8 -*-
"""Agent 设备层与 ReAct 解析静态自测（临时）。"""
import sys

sys.path.insert(0, ".")
from app.agent import agent
from app.agent.devices import find_device, get_device_client, get_devices

devs = get_devices()
print("devices:", [d.name for d in devs])

sw = find_device("core-sw-1")
c = get_device_client(sw)
print("--- display interface brief ---")
print(c.run("display interface brief"))
print("--- ping 10.0.1.2 ---")
print(c.run("ping -c 4 10.0.1.2"))

cases = [
    '{"action":"tool","name":"ping","arguments":{"device":"core-sw-1","target":"10.0.1.2"}}',
    '{"action":"finish"}',
    '```json\n{"action":"tool","name":"run_device_command","arguments":{"device":"core-rtr-1","command":"display ospf peer brief"}}\n```',
]
for t in cases:
    r = agent._parse_react(t)
    print("parse:", type(r).__name__, getattr(r, "name", ""), getattr(r, "arguments", ""))

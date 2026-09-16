"""Tool Registry：装饰器自动注册 Agent 工具。

新增工具只需：
    @register_tool(
        name="my_tool",
        description="...",
        parameters={"arg": "说明"},
        roles=["operator"],  # 允许的角色，默认 operator
    )
    async def my_tool(args: dict) -> str:
        ...

无需手动维护 TOOLS 列表和 _HANDLERS 字典。
"""
from collections import OrderedDict


class _Registry:
    def __init__(self):
        self._tools: OrderedDict[str, dict] = OrderedDict()

    def register(self, name: str, description: str, parameters: dict, roles: list[str] | None = None):
        def deco(fn):
            self._tools[name] = {
                "name": name,
                "description": description,
                "parameters": parameters,
                "handler": fn,
                "roles": roles or ["operator"],
            }
            return fn
        return deco

    def metadata(self) -> list[dict]:
        return [
            {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
            for t in self._tools.values()
        ]

    def handler(self, name: str):
        t = self._tools.get(name)
        return t["handler"] if t else None

    def roles(self, name: str) -> list[str]:
        t = self._tools.get(name)
        return t["roles"] if t else []

    def names(self) -> list[str]:
        return list(self._tools.keys())


registry = _Registry()


def register_tool(name: str, description: str, parameters: dict, roles: list[str] | None = None):
    return registry.register(name, description, parameters, roles)

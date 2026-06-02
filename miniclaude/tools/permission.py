"""权限控制 —— 工具执行前的权限检查与 CLI 确认。

通过 StructuredTool.from_function 创建权限守卫工具，
langgraph 将其识别为普通工具，避免 ToolNode 类型校验问题。
"""

import fnmatch
from typing import Callable

from langchain_core.tools import StructuredTool

READ_TOOLS = {"read", "glob", "grep"}
WRITE_TOOLS = {"write", "edit"}
DANGER_TOOLS = {"bash"}


class PermissionManager:
    """管理工具执行权限。"""

    def __init__(self):
        self._rules: list[tuple[Callable[[str, str], bool], str]] = []
        self._session_allowed: set[tuple[str, str]] = set()
        self._session_denied: set[tuple[str, str]] = set()

    def __init__(self):
        self._rules: list[tuple[Callable[[str, str], bool], str]] = []
        self._session_allowed: set[str] = set()  # 工具名 — "a" 记住整个工具
        self._session_denied: set[tuple[str, str]] = set()

    def check(self, tool_name: str, args: dict) -> tuple[bool, str]:
        if tool_name in READ_TOOLS:
            return True, "只读操作"

        key = self._extract_key(tool_name, args)

        if tool_name in self._session_allowed:
            return True, "会话已批准"
        if (tool_name, key) in self._session_denied:
            return False, "会话已拒绝"

        for match_func, action in self._rules:
            if match_func(tool_name, key):
                return action == "allow", f"规则: {action}"

        return False, "需要确认"

    def approve(self, tool_name: str, args: dict, remember: bool = False):
        if remember:
            self._session_allowed.add(tool_name)

    def deny(self, tool_name: str, args: dict, remember: bool = False):
        key = self._extract_key(tool_name, args)
        if remember:
            self._session_denied.add((tool_name, key))

    def add_rule(self, pattern: str, action: str):
        def match(tool_name: str, key: str) -> bool:
            parts = pattern.split(":", 1)
            if len(parts) != 2:
                return False
            return fnmatch.fnmatch(tool_name, parts[0]) and fnmatch.fnmatch(key, parts[1])
        self._rules.append((match, action))

    @staticmethod
    def _extract_key(tool_name: str, args: dict) -> str:
        if tool_name == "bash":
            return args.get("command", "")[:80]
        if tool_name in ("write", "edit"):
            return args.get("file_path", "")
        return ""


def wrap_tool_with_permission(
    tool,
    manager: PermissionManager,
    on_ask: Callable | None = None,
) -> StructuredTool:
    """创建权限守卫工具 — 全新的 StructuredTool，langgraph 识别为普通工具。

    on_ask(tool_name, key, args, reason) -> bool | None:
        True = 允许并记住, False = 拒绝, None = 仅本次允许
    """

    async def guarded_func(**kwargs) -> str:
        allowed, reason = manager.check(tool.name, kwargs)

        if not allowed:
            key = manager._extract_key(tool.name, kwargs)
            if on_ask:
                result = on_ask(tool.name, key, kwargs, reason)
                if result is True:
                    manager.approve(tool.name, kwargs, remember=True)
                elif result is False:
                    manager.deny(tool.name, kwargs, remember=True)
                    return (
                        f"权限被拒绝: {reason}。"
                        "用户不允许执行此操作，请不要再尝试此操作或类似操作，"
                        "换一种完全不同的方式完成任务，或告知用户无法继续。"
                    )
                else:
                    manager.approve(tool.name, kwargs, remember=False)
            else:
                return f"权限被拒绝: {reason}"

        # 调用原始工具
        return await tool.ainvoke(kwargs)

    return StructuredTool.from_function(
        coroutine=guarded_func,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
    )

"""权限控制 —— 工具执行前的权限检查与 CLI 确认。

设计：
- 每个工具注册时用权限守卫包装 ainvoke
- 权限级别：读操作自动允许，写操作需要确认，bash 每次确认
- 用户可通过 CLI 交互决定：允许(y) / 拒绝(n) / 本次会话都允许(a)
"""

import fnmatch
from typing import Callable

# 默认权限级别
READ_TOOLS = {"read", "glob", "grep"}
WRITE_TOOLS = {"write", "edit"}
DANGER_TOOLS = {"bash"}


class PermissionManager:
    """管理工具执行权限。

    支持基于规则的白名单/黑名单，以及本次会话的临时允许。
    """

    def __init__(self):
        self._rules: list[tuple[Callable[[str, str], bool], str]] = []
        self._session_allowed: set[tuple[str, str]] = set()
        self._session_denied: set[tuple[str, str]] = set()

    def check(self, tool_name: str, args: dict) -> tuple[bool, str]:
        """检查是否允许执行。

        Returns:
            (allowed, reason)
        """
        # 读工具 → 自动允许
        if tool_name in READ_TOOLS:
            return True, "只读操作"

        key = self._extract_key(tool_name, args)

        # 本次会话已决定
        if (tool_name, key) in self._session_allowed:
            return True, "会话已批准"
        if (tool_name, key) in self._session_denied:
            return False, "会话已拒绝"

        # 自定义规则
        for match_func, action in self._rules:
            if match_func(tool_name, key):
                return action == "allow", f"规则: {action}"

        # 需要确认
        return False, "需要确认"

    def approve(self, tool_name: str, args: dict, remember: bool = False):
        key = self._extract_key(tool_name, args)
        if remember:
            self._session_allowed.add((tool_name, key))

    def deny(self, tool_name: str, args: dict, remember: bool = False):
        key = self._extract_key(tool_name, args)
        if remember:
            self._session_denied.add((tool_name, key))

    def add_rule(self, pattern: str, action: str):
        """pattern 格式: 'tool_name:key_pattern'。"""
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
):
    """用权限守卫包装工具的 ainvoke。

    on_ask(tool_name, key, args, reason) -> bool | None:
        True=允许并记住, False=拒绝, None=仅本次允许
    """
    original_ainvoke = tool.ainvoke

    async def guarded_ainvoke(input_data):
        args = input_data if isinstance(input_data, dict) else {}
        allowed, reason = manager.check(tool.name, args)

        if not allowed:
            key = manager._extract_key(tool.name, args)
            if on_ask:
                result = on_ask(tool.name, key, args, reason)
                if result is True:
                    manager.approve(tool.name, args, remember=True)
                elif result is False:
                    manager.deny(tool.name, args, remember=True)
                    return f"权限被拒绝: {reason}"
                else:
                    manager.approve(tool.name, args, remember=False)
            else:
                return f"权限被拒绝: {reason}"

        return await original_ainvoke(input_data)

    # StructuredTool 是 Pydantic 模型，用 object.__setattr__ 绕过验证
    object.__setattr__(tool, "ainvoke", guarded_ainvoke)
    return tool

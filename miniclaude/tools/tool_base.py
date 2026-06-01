"""工具基类 —— 仅保留 ToolResult 用于类型标注。"""

from dataclasses import dataclass


@dataclass
class ToolResult:
    """工具执行结果（可选，方便内部做结构化错误处理）。"""
    success: bool
    content: str
    error: str | None = None

    @classmethod
    def ok(cls, content: str) -> "ToolResult":
        return cls(True, content)

    @classmethod
    def fail(cls, error: str) -> "ToolResult":
        return cls(False, "", error)

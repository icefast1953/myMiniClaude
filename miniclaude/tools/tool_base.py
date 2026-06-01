"""工具基类 —— 定义工具的抽象接口和返回类型。

所有工具必须继承 BaseTool。execute() 永远不抛异常，内部 catch 转 ToolResult。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ToolResult:
    """工具执行结果。

    Attributes:
        success: 是否执行成功
        content: 成功时的输出或失败时的错误描述
        error: 可选的错误分类码
    """
    success: bool
    content: str
    error: str | None = None


class BaseTool(ABC):
    """工具的抽象基类。

    子类必须实现 name、description、parameters 和 execute()。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称（英文），如 'read', 'write', 'bash'。"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述，供 LLM 理解何时使用此工具。"""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """参数的 JSON Schema 定义（OpenAI function calling 格式）。"""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具逻辑。

        子类应在此方法内捕获所有异常并返回 ToolResult(success=False, ...)。
        绝不向外抛出异常。
        """
        ...

    def to_schema(self) -> dict:
        """生成 OpenAI tool call schema。子类无需重写。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

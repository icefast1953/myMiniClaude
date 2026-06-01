"""工具注册中心 —— 管理所有工具的注册、查找和 Schema 生成。"""

from langchain_core.tools import BaseTool as LangChainBaseTool

from miniclaude.tools.tool_base import BaseTool


class ToolRegistry:
    """工具注册中心。管理所有已注册的工具，提供查找和 schema 生成。"""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册一个工具。同名工具会被覆盖。"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """按名称获取工具，不存在返回 None。"""
        return self._tools.get(name)

    def get_all(self) -> list[BaseTool]:
        """获取所有已注册的工具。"""
        return list(self._tools.values())

    def get_langchain_tools(self) -> list[LangChainBaseTool]:
        """获取 langchain 兼容的工具列表（用于 langgraph Agent）。"""
        return list(self._tools.values())

    def get_schemas(self) -> list[dict]:
        """生成所有工具的 OpenAI tool call schema 列表。"""
        return [tool.to_schema() for tool in self._tools.values()]

    def list_names(self) -> list[str]:
        """列出所有工具名称。"""
        return list(self._tools.keys())

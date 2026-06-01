"""工具基类 —— 继承 langchain BaseTool，保持自身 ToolResult 错误处理模式。

execute() 永远不抛异常，内部 catch 转 ToolResult。
通过 _arun() 桥接到 langchain 的 tool 执行接口。
自动从 parameters JSON Schema 生成 args_schema Pydantic 模型。
"""

from abc import abstractmethod
from dataclasses import dataclass

from langchain_core.tools import BaseTool as LangChainBaseTool
from pydantic import BaseModel, create_model


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


# 类型映射：JSON Schema type → Python type
_JSON_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _json_schema_to_pydantic(schema: dict, model_name: str = "Args") -> type[BaseModel]:
    """从 JSON Schema 动态创建 Pydantic 模型，用于 langchain args_schema。"""
    properties = schema.get("properties", {})
    required: set = set(schema.get("required", []))

    fields: dict[str, tuple[type, object]] = {}
    for name, prop in properties.items():
        field_type = _JSON_TYPE_MAP.get(prop.get("type", "string"), str)
        is_required = name in required
        default = ... if is_required else None
        fields[name] = (field_type, default)

    return create_model(model_name, **fields)  # type: ignore[arg-type]


class BaseTool(LangChainBaseTool):
    """miniClaude 工具基类。

    继承 langchain_core.tools.BaseTool，自动兼容 langgraph Agent。
    子类只需实现 name、description、parameters 和 execute()。
    args_schema 从 parameters JSON Schema 自动生成。
    """

    handle_tool_error: bool = False

    # 子类覆盖这些类属性
    name: str = ""
    description: str = ""

    def __init_subclass__(cls, **kwargs):
        """子类定义时自动从 parameters 生成 args_schema。"""
        super().__init_subclass__(**kwargs)
        params = cls.__dict__.get("parameters")
        # property 需要通过 fget 获取值
        if isinstance(params, property):
            params = params.fget(None)
        if isinstance(params, dict) and params.get("properties"):
            cls.args_schema = _json_schema_to_pydantic(params, f"{cls.__name__}Args")

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具逻辑。子类在此实现具体功能。

        绝不向外抛出异常 —— 所有异常在内部 catch
        并转为 ToolResult(success=False, ...)。
        """
        ...

    async def _arun(self, **kwargs) -> str:
        """langchain 异步执行入口。"""
        result = await self.execute(**kwargs)
        if result.success:
            return result.content
        return f"错误: {result.error or result.content}"

    def _run(self, **kwargs) -> str:
        """langchain 同步执行入口（桥接到异步）。"""
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._arun(**kwargs))

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self._arun(**kwargs))
            return future.result()

    def to_schema(self) -> dict:
        """生成 OpenAI tool call schema。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @property
    def parameters(self) -> dict:
        """参数的 JSON Schema 定义（OpenAI function calling 格式）。"""
        return {"type": "object", "properties": {}, "required": []}

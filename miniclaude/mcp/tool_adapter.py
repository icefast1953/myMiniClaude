"""MCP 工具适配器 —— MCP Tool → langchain StructuredTool。

将 MCP 工具的 JSON Schema inputSchema 转为 Pydantic args_schema。
"""

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, create_model

_TYPE_MAP = {
    "string": str, "integer": int, "number": float,
    "boolean": bool, "array": list, "object": dict,
}


def _schema_to_pydantic(schema: dict, model_name: str) -> type[BaseModel]:
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    fields: dict[str, tuple[type, object]] = {}
    for name, prop in properties.items():
        ft = _TYPE_MAP.get(prop.get("type", "string"), str)
        fields[name] = (ft, ... if name in required else None)
    return create_model(model_name, **fields)  # type: ignore


def create_langchain_tool(
    server_name: str,
    tool_name: str,
    description: str,
    input_schema: dict,
    connection,
    original_name: str,
) -> StructuredTool:
    lc_name = f"mcp_{server_name}_{tool_name}"

    async def _call(**kwargs) -> str:
        return await connection.call_tool(original_name, kwargs)

    args_model = None
    if input_schema and input_schema.get("properties"):
        args_model = _schema_to_pydantic(input_schema, lc_name)

    return StructuredTool.from_function(
        coroutine=_call,
        name=lc_name,
        description=f"[MCP:{server_name}] {description}",
        args_schema=args_model,
    )


def adapt_mcp_tools(tool_infos: list[dict]) -> list[StructuredTool]:
    tools = []
    for info in tool_infos:
        try:
            tools.append(create_langchain_tool(
                server_name=info["server"],
                tool_name=info["original_name"],
                description=info["description"],
                input_schema=info.get("input_schema", {}),
                connection=info["connection"],
                original_name=info["original_name"],
            ))
        except Exception:
            continue
    return tools

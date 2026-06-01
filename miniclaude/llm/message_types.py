"""消息类型 —— 统一使用 langchain_core.messages。

内部代码直接使用 langchain 的消息类型：
- SystemMessage
- HumanMessage（用户输入）
- AIMessage（LLM 回复，含 tool_calls）
- ToolMessage（工具执行结果）
- ToolCall

本模块提供便捷的重新导出，方便统一导入。
"""

from langchain_core.messages import (  # noqa: F401
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
)

# 类型别名（方便记忆）
AssistantMessage = AIMessage
UserMessage = HumanMessage
ToolResultMessage = ToolMessage

# 联合消息类型
Message = BaseMessage

__all__ = [
    "AIMessage",
    "AIMessageChunk",
    "AssistantMessage",
    "BaseMessage",
    "HumanMessage",
    "Message",
    "SystemMessage",
    "ToolCall",
    "ToolMessage",
    "ToolResultMessage",
    "UserMessage",
]

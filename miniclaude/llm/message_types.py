"""消息类型定义 —— 内部强类型表示 + OpenAI 格式转换。

内部统一使用 OpenAI tool call 格式。其他 LLM 后端通过 Adapter 转换为内部格式。
"""

import json
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ToolCall:
    """LLM 请求的工具调用。"""
    id: str
    name: str
    arguments: dict  # 已解析的参数字典


@dataclass
class SystemMessage:
    """系统提示消息。"""
    role: Literal["system"] = "system"
    content: str = ""


@dataclass
class UserMessage:
    """用户消息。"""
    role: Literal["user"] = "user"
    content: str = ""


@dataclass
class AssistantMessage:
    """助手回复 —— 可能包含文本 + 工具调用。"""
    role: Literal["assistant"] = "assistant"
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class ToolResultMessage:
    """工具执行结果，关联回对应的 ToolCall。"""
    role: Literal["tool"] = "tool"
    tool_call_id: str = ""
    name: str = ""
    content: str = ""


# 联合类型
Message = SystemMessage | UserMessage | AssistantMessage | ToolResultMessage


# ---- OpenAI 格式转换 ----


def messages_to_openai_format(messages: list[Message]) -> list[dict]:
    """将内部 Message 列表转为 OpenAI API 兼容的 dict 列表。"""
    result = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            result.append({"role": "system", "content": msg.content})
        elif isinstance(msg, UserMessage):
            result.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AssistantMessage):
            entry: dict = {"role": "assistant"}
            if msg.content:
                entry["content"] = msg.content
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            result.append(entry)
        elif isinstance(msg, ToolResultMessage):
            result.append({
                "role": "tool",
                "tool_call_id": msg.tool_call_id,
                "content": msg.content,
            })
    return result


def openai_response_to_message(response) -> AssistantMessage:
    """将 OpenAI chat completion response 转为 AssistantMessage。"""
    choice = response.choices[0]
    msg = choice.message

    tool_calls = []
    if msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=args,
            ))

    return AssistantMessage(
        content=msg.content,
        tool_calls=tool_calls,
    )

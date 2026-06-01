"""Agent 循环 —— 基于 langgraph create_react_agent 的 Agent 核心。"""

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from miniclaude.agent.system_prompt import SYSTEM_PROMPT, build_context_message
from miniclaude.config.app_config import Config


class AgentLoop:
    """miniClaude Agent 循环。

    封装 langgraph ReAct Agent，提供流式对话接口。
    通过回调函数与 CLI 解耦。
    """

    def __init__(
        self,
        model: ChatOpenAI,
        tools: list,
        config: Config | None = None,
    ):
        self._model = model
        self._tools = tools
        self._config = config or Config.load()
        self._agent = create_react_agent(
            model=self._model,
            tools=self._tools,
        )

    async def run(self, user_input: str, working_dir: str = ".") -> str:
        """执行一次 Agent 对话（非流式，返回最终文本）。"""
        context = build_context_message(working_dir)
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"{context}\n\n{user_input}"),
        ]

        result = await self._agent.ainvoke(
            {"messages": messages},
            config={"recursion_limit": self._config.max_turns},
        )

        # 提取最终回复（反向遍历，取最后一条 AI 文本消息）
        for msg in reversed(result.get("messages", [])):
            if (
                not isinstance(msg, HumanMessage)
                and not isinstance(msg, SystemMessage)
                and isinstance(msg.content, str)
                and msg.content
                and not (hasattr(msg, "tool_calls") and msg.tool_calls)
            ):
                return msg.content

        return ""

    async def run_stream(
        self,
        user_input: str,
        working_dir: str = ".",
        on_text: Callable[[str], None] | None = None,
        on_tool_start: Callable[[str, dict], None] | None = None,
        on_tool_end: Callable[[str, str], None] | None = None,
    ) -> str:
        """流式执行 Agent 对话，通过回调实时输出。

        Args:
            user_input: 用户输入
            working_dir: 工作目录
            on_text: 文本增量回调 (text: str) -> None
            on_tool_start: 工具开始回调 (tool_name: str, args: dict) -> None
            on_tool_end: 工具结束回调 (tool_name: str, output: str) -> None

        Returns:
            Agent 的最终文本回复。
        """
        context = build_context_message(working_dir)
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"{context}\n\n{user_input}"),
        ]

        final_text = ""
        seen_count = 2  # 已处理的消息数（system + user）

        async for event in self._agent.astream(
            {"messages": messages},
            stream_mode="values",
            config={"recursion_limit": self._config.max_turns},
        ):
            if "messages" not in event:
                continue

            all_msgs = event["messages"]
            new_msgs = all_msgs[seen_count:]

            for msg in new_msgs:
                msg_type = type(msg).__name__

                # 流式文本增量
                if msg_type == "AIMessageChunk":
                    if msg.content and on_text:
                        on_text(msg.content)

                # 完整 AI 消息
                elif msg_type == "AIMessage":
                    if msg.content and not (
                        hasattr(msg, "tool_calls") and msg.tool_calls
                    ):
                        final_text = msg.content
                    elif hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            if on_tool_start:
                                name = tc.get("name", "unknown") if isinstance(tc, dict) else getattr(tc, "name", "unknown")
                                args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                                on_tool_start(name, args)

                # 工具执行结果
                elif msg_type == "ToolMessage":
                    if on_tool_end:
                        on_tool_end(
                            getattr(msg, "name", "unknown"),
                            str(msg.content),
                        )

                seen_count += 1

        return final_text

"""Agent 循环 —— langgraph + SqliteSaver checkpoint 持久化。"""

from collections.abc import Callable
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import MessagesState
from langgraph.prebuilt import create_react_agent

from miniclaude.agent.system_prompt import SYSTEM_PROMPT, build_context_message
from miniclaude.config.app_config import Config
from miniclaude.memory.memory_manager import MemoryManager


class MiniClaudeState(MessagesState):
    """扩展 MessagesState，加入自适应压缩所需的分类上下文。

    task_context 由 TaskClassifier.profile() 写入，TokenBudgeter 读取。
    字段: {profile: dict, recent_events: list, task_history: list, stage_history: list}
    PR2 前此字段为空 dict，compact 使用默认阈值。

    remaining_steps 是 create_react_agent 的必须字段（递归限制追踪）。
    """

    remaining_steps: int
    task_context: dict


class AgentLoop:
    """miniClaude Agent — SqliteSaver 自动持久化对话状态。"""

    def __init__(
        self,
        model: ChatOpenAI,
        tools: list,
        checkpointer: SqliteSaver,
        memory_manager: MemoryManager | None = None,
        config: Config | None = None,
    ):
        self._model = model
        self._checkpointer = checkpointer
        self._memory = memory_manager
        self._config = config or Config.load()
        self._agent = create_react_agent(
            model=self._model,
            tools=tools,
            checkpointer=self._checkpointer,
            state_schema=MiniClaudeState,
        )

    def _build_input(self, user_input: str, working_dir: str,
                     is_first: bool = False) -> list:
        ctx = build_context_message(working_dir)
        if self._memory:
            mem = self._memory.get_context()
            if mem:
                ctx += f"\n\n{mem}"
        msgs = []
        if is_first:
            msgs.append(SystemMessage(content=SYSTEM_PROMPT))
        msgs.append(HumanMessage(content=f"{ctx}\n\n{user_input}"))
        return msgs

    async def run(self, user_input: str, session_id: str = "default",
                  working_dir: str = ".", is_first: bool = False) -> str:
        messages = self._build_input(user_input, working_dir, is_first)
        cfg = {
            "configurable": {"thread_id": session_id},
            "recursion_limit": self._config.max_turns,
        }
        result = await self._agent.ainvoke({"messages": messages}, config=cfg)
        return self._extract(result)

    async def run_stream(
        self, user_input: str, session_id: str = "default",
        working_dir: str = ".", is_first: bool = False,
        on_text: Callable[[str], None] | None = None,
        on_tool_start: Callable[[str, dict], None] | None = None,
        on_tool_end: Callable[[str, str], None] | None = None,
    ) -> str:
        messages = self._build_input(user_input, working_dir, is_first)
        cfg = {
            "configurable": {"thread_id": session_id},
            "recursion_limit": self._config.max_turns,
        }

        final_text = ""
        seen = len(messages)

        async for event in self._agent.astream(
            {"messages": messages}, stream_mode="values", config=cfg,
        ):
            if "messages" not in event:
                continue
            for msg in event["messages"][seen:]:
                t = type(msg).__name__
                if t == "AIMessageChunk" and msg.content and on_text:
                    on_text(msg.content)
                elif t == "AIMessage":
                    if msg.content and not (
                        hasattr(msg, "tool_calls") and msg.tool_calls
                    ):
                        final_text = msg.content
                    elif hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            if on_tool_start:
                                on_tool_start(
                                    tc.get("name", "?") if isinstance(tc, dict) else getattr(tc, "name", "?"),
                                    tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {}),
                                )
                elif t == "ToolMessage" and on_tool_end:
                    on_tool_end(getattr(msg, "name", "?"), str(msg.content))
                seen += 1
        return final_text

    @staticmethod
    def _extract(result: dict) -> str:
        for msg in reversed(result.get("messages", [])):
            if (isinstance(msg.content, str) and msg.content
                    and not (hasattr(msg, "tool_calls") and msg.tool_calls)):
                return msg.content
        return ""

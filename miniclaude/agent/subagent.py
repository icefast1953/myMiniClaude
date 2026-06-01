"""子代理 —— 特化类型的独立 Agent，星型通信，支持并行执行。

类型：
- explore: read, glob, grep（代码探索）
- research: web_fetch（查资料）
- code: read, write, edit, bash（写代码）
"""

import asyncio

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

# 各类型子代理的工具集
TOOLSET_NAMES = {
    "explore": {"read", "glob", "grep"},
    "research": {"web_fetch"},
    "code": {"read", "write", "edit", "bash"},
}

# 排除不给子代理的工具
EXCLUDED_TOOLS = {"task", "todo_write", "memory_save", "memory_recall", "memory_forget"}

SUBAGENT_PROMPT = """你是 miniClaude 子代理，类型: {agent_type}。

## 规则
1. 只完成分配给你的任务，不要做任务以外的事
2. 完成任务后直接返回结果，不要多问
3. 回复简洁，聚焦结果
4. 任务无法完成时说明原因后返回
"""


class SubagentRunner:
    """子代理执行器。支持 3 种特化类型和并行执行。"""

    def __init__(
        self,
        model: ChatOpenAI,
        all_tools: list,
        max_turns: int = 10,
    ):
        self._model = model
        self._max_turns = max_turns

        # 按名称索引所有工具
        self._tool_map: dict[str, object] = {}
        for t in all_tools:
            name = getattr(t, "name", "")
            if name and name not in EXCLUDED_TOOLS:
                self._tool_map[name] = t

    def get_tools(self, agent_type: str) -> list:
        """获取指定类型的工具子集。"""
        names = TOOLSET_NAMES.get(agent_type, TOOLSET_NAMES["explore"])
        return [self._tool_map[n] for n in names if n in self._tool_map]

    async def run(
        self,
        task: str,
        agent_type: str = "explore",
        working_dir: str = ".",
    ) -> str:
        """执行单个子任务。"""
        tools = self.get_tools(agent_type)
        prompt = SUBAGENT_PROMPT.format(agent_type=agent_type)

        agent = create_react_agent(model=self._model, tools=tools)

        result = await agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=prompt),
                    HumanMessage(
                        content=f"工作目录: {working_dir}\n\n任务: {task}\n\n"
                        "请完成任务，返回结果摘要。"
                    ),
                ]
            },
            config={"recursion_limit": self._max_turns},
        )

        for msg in reversed(result.get("messages", [])):
            if (
                isinstance(msg.content, str)
                and msg.content
                and not (hasattr(msg, "tool_calls") and msg.tool_calls)
            ):
                return msg.content

        return "子代理未返回有效结果"

    async def run_parallel(
        self,
        tasks: list[dict],
        working_dir: str = ".",
    ) -> list[str]:
        """并行执行多个子任务。

        tasks: [{"task": "...", "agent_type": "explore"}, ...]

        Returns:
            与 tasks 顺序对应的结果列表。
        """
        coros = [
            self.run(t["task"], t.get("agent_type", "explore"), working_dir)
            for t in tasks
        ]
        return await asyncio.gather(*coros)

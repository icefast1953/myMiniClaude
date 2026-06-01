"""Task 工具 —— 启动特化子代理，支持并行多任务。"""

from langchain_core.tools import StructuredTool

_SUBAGENT_RUNNER = None
_WORKING_DIR = "."


def setup_task_tool(runner, working_dir: str = ".") -> StructuredTool:
    """创建 task 工具，绑定 SubagentRunner 和工作目录。"""
    global _SUBAGENT_RUNNER, _WORKING_DIR
    _SUBAGENT_RUNNER = runner
    _WORKING_DIR = working_dir

    async def _task(description: str, agent_type: str = "explore") -> str:
        """启动特化子代理执行独立任务。子代理有独立上下文和有限工具集。

        子代理类型(agent_type):
        - explore: 只读 (read/glob/grep)，适合代码探索和信息收集
        - research: 网页获取 (web_fetch)，适合查文档和搜索资料
        - code: 读写+执行 (read/write/edit/bash)，适合重构和写代码

        支持并行：在同一次回复中多次调用 task 将并行执行。

        Args:
            description: 任务描述，越具体越好
            agent_type: 子代理类型 (explore/research/code)，默认 explore
        """
        if _SUBAGENT_RUNNER is None:
            return "错误: 子代理系统未初始化"

        try:
            result = await _SUBAGENT_RUNNER.run(description, agent_type, _WORKING_DIR)
            return f"[子代理:{agent_type}] {result}"
        except Exception as e:
            return f"子代理执行失败: {e}"

    return StructuredTool.from_function(
        coroutine=_task,
        name="task",
        description=(
            "启动特化子代理执行独立任务。"
            "agent_type: explore(探索代码)/research(查资料)/code(写代码重构)。"
            "可并行调用多个 task 同时执行不同任务。"
        ),
    )

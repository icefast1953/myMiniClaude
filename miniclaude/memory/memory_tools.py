"""记忆工具 —— 供 LLM 调用的 memory_save / memory_recall / memory_forget。"""

import os

from langchain_core.tools import tool

from miniclaude.memory.memory_manager import MemoryManager

_manager: MemoryManager | None = None


def set_memory_manager(manager: MemoryManager) -> None:
    global _manager
    _manager = manager


def _get_manager() -> MemoryManager:
    global _manager
    if _manager is None:
        _manager = MemoryManager(os.path.join(os.getcwd(), "memory"))
    return _manager


@tool("memory_save")
async def tool_memory_save(
    name: str,
    description: str,
    content: str,
    mem_type: str = "user",
) -> str:
    """保存一条记忆。用于记住用户偏好、项目约定等重要信息。

    Args:
        name: 记忆名称（kebab-case 格式，如 'user-prefs'）
        description: 一行简短摘要，用于搜索匹配
        content: 记忆的完整内容
        mem_type: user（用户偏好）| project（项目约定）| reference（参考资料）
    """
    try:
        _get_manager().save(name, description, content, mem_type)
        return f"已保存记忆: [{name}] {description}"
    except Exception as e:
        return f"错误: 保存记忆失败: {e}"


@tool("memory_recall")
async def tool_memory_recall(query: str) -> str:
    """搜索已保存的记忆。在记忆的名称、摘要和内容中查找匹配。

    Args:
        query: 搜索关键词
    """
    try:
        results = _get_manager().recall(query)
        if not results:
            return f"未找到与 '{query}' 相关的记忆"
        lines = [f"找到 {len(results)} 条记忆:"]
        for mem in results:
            lines.append(f"\n## {mem.name}")
            lines.append(f"  {mem.description}")
            lines.append(f"  {mem.content[:200]}")
        return "\n".join(lines)
    except Exception as e:
        return f"错误: 搜索记忆失败: {e}"


@tool("memory_forget")
async def tool_memory_forget(name: str) -> str:
    """删除一条记忆。

    Args:
        name: 要删除的记忆名称
    """
    try:
        if _get_manager().forget(name):
            return f"已删除记忆: {name}"
        return f"未找到记忆: {name}"
    except Exception as e:
        return f"错误: 删除记忆失败: {e}"

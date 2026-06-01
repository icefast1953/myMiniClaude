"""TodoWrite 工具 —— 管理并展示任务列表。"""

import json

from langchain_core.tools import tool


@tool("todo_write")
async def tool_todo_write(todos: str) -> str:
    """管理当前会话的任务列表。传入 JSON 数组字符串。

    每项包含 content（任务描述）和 status（pending/in_progress/completed）。

    示例:
    [{"content": "添加登录", "status": "in_progress"}, {"content": "写测试", "status": "pending"}]

    Args:
        todos: JSON 数组字符串
    """
    try:
        items = json.loads(todos)
        if not isinstance(items, list):
            return "错误: todos 必须是 JSON 数组"

        valid = {"pending", "in_progress", "completed"}
        icons = {"pending": "⬜", "in_progress": "🔄", "completed": "✅"}

        lines = ["# 任务列表", ""]
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                return f"错误: 第 {i + 1} 项不是有效的 JSON 对象"
            content = item.get("content", "")
            status = item.get("status", "pending")
            if status not in valid:
                return f"错误: 第 {i + 1} 项 status 无效: {status}"
            lines.append(f"{icons.get(status, '⬜')} {content} [{status}]")

        lines.append("")
        lines.append(f"共 {len(items)} 项任务")
        return "\n".join(lines)

    except json.JSONDecodeError as e:
        return f"错误: 无效 JSON: {e}"
    except Exception as e:
        return f"错误: {e}"

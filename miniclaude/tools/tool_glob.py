"""Glob 工具 —— 基于 glob 模式匹配文件路径。"""

from pathlib import Path

from langchain_core.tools import tool


@tool("glob")
async def tool_glob(pattern: str, path: str = ".") -> str:
    """按 glob 模式匹配文件路径。支持 ** 递归匹配。
    结果按修改时间降序排列（最近修改的在前），最多返回 500 条。

    Args:
        pattern: glob 匹配模式，如 '**/*.py' 或 'src/**/*.ts'
        path: 搜索起始目录，默认为当前工作目录
    """
    try:
        search_path = Path(path)
        if not search_path.exists():
            return f"错误: 路径不存在: {path}"

        matches = list(search_path.glob(pattern))

        if not matches:
            return "未找到匹配的文件"

        matches.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

        total = len(matches)
        matches = matches[:500]

        output_lines = [str(m) for m in matches]
        if total > 500:
            output_lines.append(f"\n... 还有 {total - 500} 个结果未显示")

        return "\n".join(output_lines)

    except Exception as e:
        return f"错误: glob 搜索时出错: {e}"

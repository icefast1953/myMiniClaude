"""Read 工具 —— 读取文件内容，支持分页和行号。"""

from pathlib import Path

from langchain_core.tools import tool


@tool("read")
async def tool_read(file_path: str, offset: int = 1, limit: int = 2000) -> str:
    """读取文件内容。返回带行号的文本（类似 cat -n 格式）。

    支持 offset 和 limit 参数实现分页读取。
    默认最多读取 2000 行。会自动检测并拒绝二进制文件。

    Args:
        file_path: 要读取的文件的绝对路径
        offset: 起始行号（1-based），默认从头开始
        limit: 最大读取行数，默认 2000
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return f"错误: 文件不存在: {file_path}"
        if not path.is_file():
            return f"错误: 路径不是文件: {file_path}"

        with open(path, "rb") as f:
            if b"\x00" in f.read(8192):
                return f"错误: 文件是二进制格式，无法读取: {file_path}"

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        start = max(0, offset - 1)
        end = min(total_lines, start + limit)
        selected = lines[start:end]

        output_lines = []
        for i, line in enumerate(selected, start=start + 1):
            output_lines.append(f"{i}\t{line.rstrip()}")

        output = "\n".join(output_lines)
        if end < total_lines:
            remaining = total_lines - end
            output += f"\n\n... 还有 {remaining} 行（共 {total_lines} 行），使用 offset={end + 1} 继续读取"

        return output

    except PermissionError:
        return f"错误: 权限不足，无法读取: {file_path}"
    except Exception as e:
        return f"错误: 读取文件时出错: {e}"

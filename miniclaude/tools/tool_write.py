"""Write 工具 —— 写入文件内容，自动创建父目录。"""

from pathlib import Path

from langchain_core.tools import tool


@tool("write")
async def tool_write(file_path: str, content: str) -> str:
    """将内容写入文件。如果文件已存在则覆盖，如果父目录不存在则自动创建。

    Args:
        file_path: 要写入的文件的绝对路径
        content: 要写入的完整内容
    """
    try:
        path = Path(file_path)

        if path.exists() and path.is_dir():
            return f"错误: 目标路径是目录，无法写入: {file_path}"

        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        size = path.stat().st_size
        line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)

        return f"已写入: {file_path}\n大小: {size} 字节\n行数: {line_count}"

    except PermissionError:
        return f"错误: 权限不足，无法写入: {file_path}"
    except Exception as e:
        return f"错误: 写入文件时出错: {e}"

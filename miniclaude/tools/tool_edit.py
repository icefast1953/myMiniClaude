"""Edit 工具 —— 精确字符串替换（非正则），唯一性检查保证编辑安全。"""

from pathlib import Path

from langchain_core.tools import tool


@tool("edit")
async def tool_edit(file_path: str, old_text: str, new_text: str) -> str:
    """对文件执行精确字符串替换（非正则表达式）。

    在文件中查找 old_text，必须恰好出现 1 次才执行替换。
    如果出现 0 次或多次，将返回错误并提示原因。

    Args:
        file_path: 要编辑的文件的绝对路径
        old_text: 要被替换的原始文本，必须在文件中恰好出现 1 次
        new_text: 替换后的新文本
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return f"错误: 文件不存在: {file_path}"
        if not path.is_file():
            return f"错误: 路径不是文件: {file_path}"

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        count = content.count(old_text)

        if count == 0:
            return "错误: 未找到匹配的文本。请确认 old_text 与文件内容完全一致（包括缩进和换行）。"
        if count > 1:
            return f"错误: 找到 {count} 处匹配的文本。请提供更多上下文使 old_text 在文件中唯一。"

        new_content = content.replace(old_text, new_text, 1)

        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return f"已编辑: {file_path}\n替换了 1 处文本"

    except PermissionError:
        return f"错误: 权限不足，无法编辑: {file_path}"
    except Exception as e:
        return f"错误: 编辑文件时出错: {e}"

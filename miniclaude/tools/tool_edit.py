"""Edit 工具 —— 精确字符串替换（非正则），唯一性检查保证编辑安全。"""

from pathlib import Path

from miniclaude.tools.tool_base import BaseTool, ToolResult


class ToolEdit(BaseTool):
    """精确字符串替换编辑器。仿 Claude Code 的 Edit 行为。"""

    name: str = "edit"
    description: str = (
        "对文件执行精确字符串替换（非正则表达式）。"
        "在文件中查找 old_text，必须恰好出现 1 次才执行替换。"
        "如果出现 0 次或多次，将返回错误并提示原因。"
    )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要编辑的文件的绝对路径",
                },
                "old_text": {
                    "type": "string",
                    "description": "要被替换的原始文本，必须在文件中恰好出现 1 次",
                },
                "new_text": {
                    "type": "string",
                    "description": "替换后的新文本",
                },
            },
            "required": ["file_path", "old_text", "new_text"],
        }

    async def execute(
        self,
        file_path: str,
        old_text: str,
        new_text: str,
    ) -> ToolResult:
        try:
            path = Path(file_path)
            if not path.exists():
                return ToolResult(False, "", f"文件不存在: {file_path}")
            if not path.is_file():
                return ToolResult(False, "", f"路径不是文件: {file_path}")

            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            count = content.count(old_text)

            if count == 0:
                return ToolResult(
                    False, "",
                    f"未找到匹配的文本。请确认 old_text 与文件内容完全一致（包括缩进和换行）。",
                )
            if count > 1:
                return ToolResult(
                    False, "",
                    f"找到 {count} 处匹配的文本。请提供更多上下文使 old_text 在文件中唯一。",
                )

            new_content = content.replace(old_text, new_text, 1)

            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return ToolResult(True, f"已编辑: {file_path}\n替换了 1 处文本")

        except PermissionError:
            return ToolResult(False, "", f"权限不足，无法编辑: {file_path}")
        except Exception as e:
            return ToolResult(False, "", f"编辑文件时出错: {e}")

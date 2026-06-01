"""Write 工具 —— 写入文件内容，自动创建父目录。"""

from pathlib import Path

from miniclaude.tools.tool_base import BaseTool, ToolResult


class ToolWrite(BaseTool):
    """写入/覆盖文件内容。自动创建不存在的父目录。"""

    name: str = "write"
    description: str = (
        "将内容写入文件。如果文件已存在则覆盖，"
        "如果父目录不存在则自动创建。"
        "返回写入的文件路径、大小和行数。"
    )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要写入的文件的绝对路径",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的完整内容",
                },
            },
            "required": ["file_path", "content"],
        }

    async def execute(self, file_path: str, content: str) -> ToolResult:
        try:
            path = Path(file_path)

            if path.exists() and path.is_dir():
                return ToolResult(False, "", f"目标路径是目录，无法写入: {file_path}")

            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            size = path.stat().st_size
            line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)

            return ToolResult(
                True,
                f"已写入: {file_path}\n大小: {size} 字节\n行数: {line_count}",
            )

        except PermissionError:
            return ToolResult(False, "", f"权限不足，无法写入: {file_path}")
        except Exception as e:
            return ToolResult(False, "", f"写入文件时出错: {e}")

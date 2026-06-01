"""Read 工具 —— 读取文件内容，支持分页和行号。"""

from pathlib import Path

from miniclaude.tools.tool_base import BaseTool, ToolResult


class ToolRead(BaseTool):
    """读取文件内容，模拟 cat -n 格式输出带行号的文本。"""

    name: str = "read"
    description: str = (
        "读取文件内容。返回带行号的文本（类似 cat -n 格式）。"
        "支持 offset 和 limit 参数实现分页读取。"
        "默认最多读取 2000 行。会自动检测并拒绝二进制文件。"
    )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要读取的文件的绝对路径",
                },
                "offset": {
                    "type": "integer",
                    "description": "起始行号（1-based），默认从头开始",
                },
                "limit": {
                    "type": "integer",
                    "description": "最大读取行数，默认 2000",
                },
            },
            "required": ["file_path"],
        }

    async def execute(
        self,
        file_path: str,
        offset: int = 1,
        limit: int = 2000,
    ) -> ToolResult:
        try:
            path = Path(file_path)
            if not path.exists():
                return ToolResult(False, "", f"文件不存在: {file_path}")
            if not path.is_file():
                return ToolResult(False, "", f"路径不是文件: {file_path}")

            # 二进制文件检测：读前 8KB 检查 null 字节
            with open(path, "rb") as f:
                head = f.read(8192)
            if b"\x00" in head:
                return ToolResult(False, "", f"文件是二进制格式，无法读取: {file_path}")

            # 读取并添加行号
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

            return ToolResult(True, output)

        except PermissionError:
            return ToolResult(False, "", f"权限不足，无法读取: {file_path}")
        except Exception as e:
            return ToolResult(False, "", f"读取文件时出错: {e}")

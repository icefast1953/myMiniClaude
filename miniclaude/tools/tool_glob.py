"""Glob 工具 —— 基于 glob 模式匹配文件路径。"""

from pathlib import Path

from miniclaude.tools.tool_base import BaseTool, ToolResult


class ToolGlob(BaseTool):
    """按 glob 模式匹配文件路径。结果按修改时间降序排列。"""

    name: str = "glob"
    description: str = (
        "按 glob 模式匹配文件路径。"
        "支持 ** 递归匹配。"
        "结果按修改时间降序排列（最近修改的在前），最多返回 500 条。"
    )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "glob 匹配模式，如 '**/*.py' 或 'src/**/*.ts'",
                },
                "path": {
                    "type": "string",
                    "description": "搜索起始目录，默认为当前工作目录",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, pattern: str, path: str = ".") -> ToolResult:
        try:
            search_path = Path(path)
            if not search_path.exists():
                return ToolResult(False, "", f"路径不存在: {path}")

            matches = list(search_path.glob(pattern))

            if not matches:
                return ToolResult(True, "未找到匹配的文件")

            matches.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

            total = len(matches)
            matches = matches[:500]

            output_lines = [str(m) for m in matches]
            if total > 500:
                output_lines.append(f"\n... 还有 {total - 500} 个结果未显示")

            return ToolResult(True, "\n".join(output_lines))

        except Exception as e:
            return ToolResult(False, "", f"glob 搜索时出错: {e}")

"""Grep 工具 —— 基于正则表达式的代码内容搜索。"""

import re
from pathlib import Path

from miniclaude.tools.tool_base import BaseTool, ToolResult


class ToolGrep(BaseTool):
    """在文件内容中搜索正则表达式匹配。支持大小写控制、glob 过滤、多种输出模式。"""

    name: str = "grep"
    description: str = (
        "在文件内容中搜索正则表达式匹配。"
        "支持大小写敏感控制、glob 文件过滤、多种输出模式。"
        "自动跳过二进制文件，结果最多返回 250 条。"
    )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "正则表达式搜索模式",
                },
                "path": {
                    "type": "string",
                    "description": "搜索目录或文件路径，默认为当前工作目录",
                },
                "glob": {
                    "type": "string",
                    "description": "文件过滤 glob 模式，如 '*.py' 或 '**/*.ts'",
                },
                "ignore_case": {
                    "type": "boolean",
                    "description": "是否忽略大小写，默认 false（区分大小写）",
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_with_matches", "count"],
                    "description": "输出模式：content（显示匹配行）、files_with_matches（仅文件路径）、count（匹配计数）",
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        glob: str | None = None,
        ignore_case: bool = False,
        output_mode: str = "content",
    ) -> ToolResult:
        try:
            flags = re.IGNORECASE if ignore_case else 0
            try:
                regex = re.compile(pattern, flags)
            except re.error as e:
                return ToolResult(False, "", f"无效的正则表达式: {e}")

            search_path = Path(path)
            if not search_path.exists():
                return ToolResult(False, "", f"路径不存在: {path}")

            if search_path.is_file():
                files = [search_path]
            else:
                if glob:
                    files = list(search_path.rglob(glob))
                else:
                    files = [p for p in search_path.rglob("*") if p.is_file()]
                files = files[:1000]

            results: list[str] = []

            for file_path in sorted(files):
                if not file_path.is_file():
                    continue
                if self._is_binary(file_path):
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()

                    file_matches = []
                    for line_num, line in enumerate(lines, 1):
                        if regex.search(line):
                            file_matches.append((line_num, line.rstrip()))

                    if file_matches:
                        if output_mode == "count":
                            results.append(f"{file_path}: {len(file_matches)} 处匹配")
                        elif output_mode == "files_with_matches":
                            results.append(str(file_path))
                        else:
                            for line_num, line in file_matches:
                                results.append(f"{file_path}:{line_num}: {line}")

                except Exception:
                    continue

                if len(results) >= 250:
                    results.append("... 结果已截断（超过 250 条）")
                    break

            if not results:
                return ToolResult(True, "未找到匹配结果")

            return ToolResult(True, "\n".join(results))

        except Exception as e:
            return ToolResult(False, "", f"搜索时出错: {e}")

    @staticmethod
    def _is_binary(file_path: Path) -> bool:
        try:
            with open(file_path, "rb") as f:
                head = f.read(8192)
            return b"\x00" in head
        except Exception:
            return True

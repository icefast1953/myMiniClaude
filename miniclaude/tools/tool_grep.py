"""Grep 工具 —— 基于正则表达式的代码内容搜索。"""

import re
from pathlib import Path

from langchain_core.tools import tool


def _is_binary(file_path: Path) -> bool:
    try:
        with open(file_path, "rb") as f:
            return b"\x00" in f.read(8192)
    except Exception:
        return True


@tool("grep")
async def tool_grep(
    pattern: str,
    path: str = ".",
    glob: str | None = None,
    ignore_case: bool = False,
    output_mode: str = "content",
) -> str:
    """在文件内容中搜索正则表达式匹配。

    支持大小写敏感控制、glob 文件过滤、多种输出模式。
    自动跳过二进制文件，结果最多返回 250 条。

    Args:
        pattern: 正则表达式搜索模式
        path: 搜索目录或文件路径，默认为当前工作目录
        glob: 文件过滤 glob 模式，如 '*.py' 或 '**/*.ts'
        ignore_case: 是否忽略大小写，默认 false
        output_mode: 输出模式 (content/files_with_matches/count)
    """
    try:
        flags = re.IGNORECASE if ignore_case else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return f"错误: 无效的正则表达式: {e}"

        search_path = Path(path)
        if not search_path.exists():
            return f"错误: 路径不存在: {path}"

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
            if not file_path.is_file() or _is_binary(file_path):
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
            return "未找到匹配结果"

        return "\n".join(results)

    except Exception as e:
        return f"错误: 搜索时出错: {e}"

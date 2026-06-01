"""Bash 工具 —— 执行 Shell 命令，带超时和输出截断。"""

import subprocess

from miniclaude.tools.tool_base import BaseTool, ToolResult


class ToolBash(BaseTool):
    """执行 Shell 命令。安全措施：超时控制 + 输出截断 + 工作目录隔离。"""

    name: str = "bash"
    description: str = (
        "在当前工作目录中执行 Shell 命令。"
        "返回 stdout、stderr 和退出码。"
        "输出最多截断为 100KB。"
        "使用 timeout 参数控制超时秒数（默认 120）。"
    )

    def __init__(self, working_dir: str = ".", **kwargs):
        super().__init__(**kwargs)
        self._cwd = working_dir

    def set_working_dir(self, path: str) -> None:
        """更新工作目录。"""
        self._cwd = path

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 Shell 命令",
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数，默认 120",
                },
                "description": {
                    "type": "string",
                    "description": "命令的简短描述，说明用途",
                },
            },
            "required": ["command", "description"],
        }

    async def execute(
        self,
        command: str,
        description: str = "",
        timeout: int = 120,
    ) -> ToolResult:
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self._cwd,
            )

            stdout = self._truncate(result.stdout, 100_000)
            stderr = self._truncate(result.stderr, 100_000)

            output_parts = []
            if stdout:
                output_parts.append(stdout)
            if stderr:
                output_parts.append(f"[stderr]\n{stderr}")
            if result.returncode != 0:
                output_parts.append(f"[退出码: {result.returncode}]")

            output = "\n".join(output_parts) if output_parts else "(无输出)"
            success = result.returncode == 0

            return ToolResult(success, output)

        except subprocess.TimeoutExpired:
            return ToolResult(False, "", f"命令超时（{timeout} 秒）: {command}")
        except FileNotFoundError:
            return ToolResult(False, "", f"命令未找到: {command.split()[0] if command else command}")
        except Exception as e:
            return ToolResult(False, "", f"执行命令时出错: {e}")

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return (
            text[:half]
            + f"\n\n... [截断 {len(text) - max_chars} 字符] ...\n\n"
            + text[-half:]
        )

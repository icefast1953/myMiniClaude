"""Bash 工具 —— 执行 Shell 命令，带超时和输出截断。"""

import subprocess

from langchain_core.tools import StructuredTool, tool


def create_tool_bash(working_dir: str = ".") -> StructuredTool:
    """创建 Bash 工具，绑定到指定的工作目录。

    因为 tool_bash 需要 working_dir 状态，
    使用工厂函数而不是 @tool 装饰器。
    """

    async def _bash(
        command: str,
        description: str = "",
        timeout: int = 120,
    ) -> str:
        """在当前工作目录中执行 Shell 命令。

        返回 stdout、stderr 和退出码。输出最多截断 100KB。

        Args:
            command: 要执行的 Shell 命令
            description: 命令的简短说明（用于审核）
            timeout: 超时秒数，默认 120
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir,
            )

            def _truncate(text: str, max_chars: int = 100_000) -> str:
                if len(text) <= max_chars:
                    return text
                half = max_chars // 2
                return (
                    text[:half]
                    + f"\n\n... [截断 {len(text) - max_chars} 字符] ...\n\n"
                    + text[-half:]
                )

            stdout = _truncate(result.stdout)
            stderr = _truncate(result.stderr)

            output_parts = []
            if stdout:
                output_parts.append(stdout)
            if stderr:
                output_parts.append(f"[stderr]\n{stderr}")
            if result.returncode != 0:
                output_parts.append(f"[退出码: {result.returncode}]")

            output = "\n".join(output_parts) if output_parts else "(无输出)"

            if result.returncode != 0:
                return f"错误: 命令执行失败\n{output}"

            return output

        except subprocess.TimeoutExpired:
            return f"错误: 命令超时（{timeout} 秒）: {command}"
        except FileNotFoundError:
            return f"错误: 命令未找到: {command.split()[0] if command else command}"
        except Exception as e:
            return f"错误: 执行命令时出错: {e}"

    return StructuredTool.from_function(
        coroutine=_bash,
        name="bash",
        description="在当前工作目录中执行 Shell 命令。返回 stdout/stderr 和退出码。输出最多截断 100KB。",
    )

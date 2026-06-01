"""Rich Console —— miniClaude 的 CLI 视觉封装。

统一管理所有终端输出元素：用户消息、助手流式回复、工具调用状态等。
"""

from rich.console import Console
from rich.status import Status

from miniclaude.cli.markdown_render import MarkdownRenderer


class RichConsole:
    """miniClaude 控制台输出封装。

    视觉规范：
    - 用户: 蓝色 [用户]
    - 助手: 绿色 [miniClaude]，内容 Markdown 渲染
    - 工具调用: 黄色 🔧
    - 工具结果成功: 绿色 ✓
    - 工具结果失败: 红色 ✗
    - 思考中: Spinner 动画
    """

    def __init__(self):
        self._console = Console()
        self._renderer = MarkdownRenderer(self._console)
        self._status: Status | None = None

    # ---- 用户消息 ----

    def print_user(self, text: str) -> None:
        """打印用户输入（蓝色前缀）。"""
        self._console.print(f"[bold blue]You[/] {text}")

    # ---- 助手流式输出 ----

    def start_assistant(self) -> None:
        """开始流式渲染助手回复。"""
        self._console.print("[bold green]miniClaude[/] ", end="")

    def render_stream(self, delta: str) -> None:
        """在流式会话中追加文本增量。首次调用时自动启动 MarkdownRenderer。"""
        if self._renderer.buffer == "" and self._renderer._live is None:
            self._renderer.start()
        self._renderer.append(delta)

    def finish_assistant(self) -> str:
        """结束流的式渲染，返回完整文本。"""
        return self._renderer.finish()

    # ---- 工具调用展示 ----

    def show_tool_call(self, name: str, args: dict) -> None:
        """显示工具调用信息。"""
        args_preview = self._format_args(args)
        self._console.print(f"  [bold yellow]🔧 {name}[/] {args_preview}")

    def show_tool_result(self, name: str, output: str, success: bool = True) -> None:
        """显示工具执行结果。"""
        icon = "[bold green]✓[/]" if success else "[bold red]✗[/]"
        preview = self._truncate(output.strip(), 200)
        self._console.print(f"  {icon} [dim]{name}: {preview}[/dim]")

    # ---- 状态指示 ----

    def show_thinking(self) -> None:
        """显示 '思考中...' Spinner。"""
        self._status = self._console.status("[dim]思考中...[/dim]", spinner="dots")
        self._status.start()

    def hide_thinking(self) -> None:
        """隐藏 Spinner。"""
        if self._status:
            self._status.stop()
            self._status = None

    # ---- 系统消息 ----

    def print_error(self, msg: str) -> None:
        """打印错误消息。"""
        self._console.print(f"[bold red]错误:[/] {msg}")

    def print_system(self, msg: str) -> None:
        """打印系统消息（灰色）。"""
        self._console.print(f"[dim]{msg}[/dim]")

    def print_welcome(self) -> None:
        """打印欢迎信息。"""
        self._console.print()
        self._console.print("[bold]miniClaude[/] v0.1.0 — AI 编程助手")
        self._console.print("[dim]输入消息开始对话，/exit 退出，/help 帮助[/dim]")
        self._console.print()

    # ---- 用户输入 ----

    def prompt_user(self) -> str:
        """获取用户输入。"""
        from rich.prompt import PromptBase

        class _SimplePrompt(PromptBase[str]):
            prompt_suffix = ""

        return _SimplePrompt.ask("")

    # ---- 内部工具 ----

    @staticmethod
    def _format_args(args: dict) -> str:
        """格式化工具参数为简短预览。"""
        items = []
        for k, v in args.items():
            s = str(v)
            if len(s) > 60:
                s = s[:57] + "..."
            items.append(f"{k}={s}")
        return ", ".join(items)

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        """截断文本到指定长度。"""
        if len(text) <= max_chars:
            return text
        return text[:max_chars - 3] + "..."

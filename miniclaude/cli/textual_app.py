"""Textual TUI —— 全终端 UI 版本的 miniClaude。

布局: Header + Chat(RichLog) + Input + Footer
"""

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Footer, Header, Input, RichLog


class MiniClaudeTUI(App):
    """miniClaude Textual TUI。"""

    CSS = """
    #chat { height: 1fr; border: none; background: $surface; }
    #input-container { height: auto; padding: 0 1; border-top: solid $primary; }
    #prompt { width: 100%; }
    """

    def __init__(self, agent, config):
        super().__init__()
        self._agent = agent
        self._config = config
        self._working_dir = "."
        self._running = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="chat", highlight=True, markup=True, wrap=True)
        with Container(id="input-container"):
            yield Input(id="prompt", placeholder="输入消息，/exit 退出...")
        yield Footer()

    def on_mount(self) -> None:
        chat = self.query_one("#chat", RichLog)
        chat.write("[bold]miniClaude[/] v0.1.0 — AI 编程助手")
        chat.write("[dim]输入消息开始对话，/exit 退出，/help 帮助[/dim]")
        chat.write("")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_input = event.value.strip()
        if not user_input:
            return

        inp = self.query_one("#prompt", Input)
        inp.clear()
        chat = self.query_one("#chat", RichLog)

        # 命令处理
        if user_input.startswith("/"):
            self._handle_command(user_input, chat)
            return

        if self._running:
            chat.write("[dim]请等待当前请求完成...[/dim]")
            return

        self._running = True
        inp.disabled = True
        chat.write(f"[bold blue]You[/] {user_input}")

        try:
            pending: list[str] = []
            await self._agent.run_stream(
                user_input,
                working_dir=self._working_dir,
                context_injection="",
                on_text=lambda t: chat.write(t, animate=False),
                on_tool_start=lambda n, a: pending.append(
                    f"  [bold yellow]🔧 {n}[/] {self._fmt(a)}"
                ),
                on_tool_end=lambda n, o: (
                    chat.write(pending.pop(0) if pending else f"  🔧 {n}"),
                    chat.write(f"  [dim]  ✓ {o[:100]}[/dim]"),
                ),
            )
        except Exception as e:
            chat.write(f"[bold red]错误: {e}[/]")

        chat.write("")
        self._running = False
        inp.disabled = False
        inp.focus()

    def _handle_command(self, cmd: str, chat: RichLog) -> None:
        """处理 / 命令。"""
        cmd = cmd.strip().lower()
        if cmd == "/exit":
            self.exit()
        elif cmd == "/help":
            chat.write("[bold]可用命令:[/]")
            chat.write("  /exit   — 退出程序")
            chat.write("  /help   — 显示帮助")
            chat.write("  /clear  — 清空对话")
            chat.write("  /model  — 模型信息")
            chat.write(f"  [dim]当前模型: {self._config.llm_model}[/dim]")
        elif cmd == "/clear":
            chat.clear()
            chat.write("[dim]对话已清空[/dim]")
        elif cmd == "/model":
            chat.write(
                f"[dim]模型: {self._config.llm_model} | "
                f"API: {self._config.llm_base_url} | "
                f"最大轮次: {self._config.max_turns}[/dim]"
            )
        else:
            chat.write(f"[dim]未知命令: {cmd}，/help 查看帮助[/dim]")

    @staticmethod
    def _fmt(args: dict) -> str:
        parts = []
        for k, v in args.items():
            s = str(v)
            if len(s) > 50:
                s = s[:47] + "..."
            parts.append(f"{k}={s}")
        return ", ".join(parts)

    def set_working_dir(self, path: str) -> None:
        self._working_dir = path

"""Markdown 流式渲染器 —— 基于 rich.live.Live 实现逐 token 实时渲染。"""

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown


class MarkdownRenderer:
    """封装 rich.live.Live + Markdown，实现流式 Markdown 渲染。

    用法:
        renderer = MarkdownRenderer(console)
        renderer.start()
        for token in stream:
            renderer.append(token)
        text = renderer.finish()
    """

    def __init__(self, console: Console):
        self._console = console
        self._buffer = ""
        self._live: Live | None = None

    def start(self) -> None:
        """开始渲染会话。"""
        self._buffer = ""
        self._live = Live(
            Markdown(""),
            console=self._console,
            refresh_per_second=10,
            vertical_overflow="visible",
        )
        self._live.start()

    def append(self, text: str) -> None:
        """追加文本增量并刷新渲染。"""
        self._buffer += text
        if self._live:
            self._live.update(Markdown(self._buffer))

    def finish(self) -> str:
        """结束渲染，返回完整文本。"""
        if self._live:
            self._live.stop()
            self._live = None
        return self._buffer

    @property
    def buffer(self) -> str:
        """当前已累积的文本。"""
        return self._buffer

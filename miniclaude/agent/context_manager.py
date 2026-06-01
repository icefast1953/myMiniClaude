"""上下文管理 —— 滑动窗口 + Summary 压缩策略。

仿 Claude Code 的上下文管理：
- 滑动窗口：保留最近 N 轮完整对话
- Summary：旧对话由 LLM 总结，增量合并
- 窗口溢出时自动触发压缩提示
- 支持 PostgreSQL 持久化（可选）
"""

from dataclasses import dataclass


@dataclass
class TurnRecord:
    """一轮对话的完整记录。"""
    user_input: str
    assistant_response: str
    tool_calls_summary: str = ""  # 工具调用的简短摘要


class ContextManager:
    """滑动窗口 + 增量 Summary 的上下文管理器。

    窗口结构:
    ┌─────────────────────────┬──────────────────────────┐
    │  Summary (压缩的历史)    │  Window (最近 N 轮完整)   │
    │  由 LLM 增量生成         │  保留完整 user/assistant  │
    └─────────────────────────┴──────────────────────────┘
    """

    def __init__(self, window_size: int = 10, max_turns: int = 20):
        self._summary: str = ""           # LLM 生成的累计摘要
        self._window: list[TurnRecord] = []
        self._window_size = window_size
        self._max_turns = max_turns       # 总共保留的最大轮次（摘要计入）
        self._total_turns = 0
        self._total_chars = 0

    def add_turn(
        self,
        user_input: str,
        assistant_response: str,
        tool_calls: list[str] | None = None,
    ) -> None:
        """添加一轮对话到窗口。"""
        tools_str = "; ".join(tool_calls) if tool_calls else ""
        turn = TurnRecord(
            user_input=user_input,
            assistant_response=assistant_response,
            tool_calls_summary=tools_str,
        )
        self._window.append(turn)
        self._total_turns += 1
        self._total_chars += len(user_input) + len(assistant_response)

    @property
    def turn_count(self) -> int:
        return self._total_turns

    @property
    def window_count(self) -> int:
        return len(self._window)

    def should_compact(self) -> bool:
        """窗口是否溢出？"""
        return len(self._window) >= self._window_size or self._total_turns >= self._max_turns

    def compact(self, new_summary: str) -> None:
        """将当前窗口压缩为摘要，合并到已有 summary。

        调用前应先让 LLM 生成 new_summary。
        压缩后窗口清空，summary 更新。
        """
        if self._summary:
            self._summary = (
                f"{self._summary}\n\n[后续对话摘要]\n{new_summary}"
            )
        else:
            self._summary = new_summary
        self._window.clear()

    def get_injection(self) -> str:
        """生成注入到新对话的完整上下文。"""
        parts = []

        # Summary 部分
        if self._summary:
            parts.append(f"[对话历史摘要]\n{self._summary}")

        # 滑动窗口部分（最近 N 轮完整对话）
        if self._window:
            lines = ["[最近对话]"]
            for t in self._window[-self._window_size:]:
                lines.append(f"用户: {t.user_input[:200]}")
                if t.tool_calls_summary:
                    lines.append(f"[工具调用: {t.tool_calls_summary}]")
                # 截断过长的回复
                resp = t.assistant_response
                if len(resp) > 300:
                    resp = resp[:300] + "..."
                lines.append(f"助手: {resp}")
            parts.append("\n".join(lines))

        return "\n\n".join(parts) if parts else ""

    def build_compact_prompt(self) -> str:
        """构建给 LLM 的 compact 请求：总结窗口中的对话。"""
        if not self._window:
            return ""

        turns_desc = []
        for i, t in enumerate(self._window):
            turns_desc.append(
                f"第{i+1}轮 - 用户: {t.user_input[:200]}\n"
                f"助手: {t.assistant_response[:300]}"
            )

        return (
            "请用 200-300 字总结以下对话的关键信息，"
            "包括用户的需求、做出的决策、遇到的问题和解决方案：\n\n"
            + "\n\n".join(turns_desc)
        )

    def estimate_tokens(self) -> int:
        """估算当前上下文 token 数。"""
        chars = self._total_chars
        if self._summary:
            chars += len(self._summary)
        return int(chars / 3.5)

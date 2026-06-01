"""上下文管理 —— 追踪对话轮次、估算 token、支持 compact 压缩。

仿 Claude Code 的 /compact 机制：
- 追踪每轮对话
- 估算 token 用量
- 超过阈值触发压缩：用 LLM 总结历史 → 注入后续对话
"""

from dataclasses import dataclass


@dataclass
class TurnRecord:
    user_input: str
    assistant_summary: str  # 助手回复前 200 字符


class ContextManager:
    """REPL 层面的跨轮次上下文管理。"""

    def __init__(self, max_turns: int = 20):
        self._turns: list[TurnRecord] = []
        self._compact_summary: str = ""
        self._max_turns = max_turns
        self._total_chars = 0

    def add_turn(self, user_input: str, assistant_response: str) -> None:
        self._turns.append(TurnRecord(user_input, assistant_response[:200]))
        self._total_chars += len(user_input) + len(assistant_response)

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    def should_compact(self) -> bool:
        return len(self._turns) >= self._max_turns

    def estimate_tokens(self) -> int:
        return int(self._total_chars / 3.5)

    def compact(self, summary: str) -> None:
        """用 LLM 生成的总结替换历史。"""
        self._compact_summary = summary
        self._turns.clear()
        self._total_chars = 0

    def get_injection(self) -> str:
        """生成注入到新对话的上下文摘要。"""
        parts = []
        if self._compact_summary:
            parts.append(f"[对话历史摘要]\n{self._compact_summary}")
        if self._turns:
            recent = [f"用户: {t.user_input[:100]}" for t in self._turns[-5:]]
            parts.append("[最近对话]\n" + "\n".join(recent))
        return "\n\n".join(parts) if parts else ""

    def build_compact_prompt(self) -> str:
        """构建给 LLM 的 compact 提示词。"""
        if not self._turns:
            return ""
        lines = ["请总结以下对话历史的关键信息，200 字以内："]
        for t in self._turns:
            lines.append(f"- 用户: {t.user_input[:150]}")
            lines.append(f"  助手: {t.assistant_summary[:150]}")
        return "\n".join(lines)

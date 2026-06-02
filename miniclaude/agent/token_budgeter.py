"""Token Budgeter —— 监控对话 token 用量，触发 compact。

配合 SqliteSaver checkpoint 读取消息列表，估算 token 用量。
"""

from dataclasses import dataclass

CHARS_PER_TOKEN = 3.5
WARNING_THRESHOLD = 4000
COMPACT_THRESHOLD = 8000
KEEP_RECENT = 5


@dataclass
class BudgetStatus:
    total_tokens: int
    message_count: int
    should_warn: bool
    should_compact: bool
    compact_prompt: str


class TokenBudgeter:
    """Token 预算管理器。"""

    def __init__(self, warning: int = WARNING_THRESHOLD,
                 compact: int = COMPACT_THRESHOLD,
                 keep: int = KEEP_RECENT):
        self._warning = warning
        self._compact = compact
        self._keep = keep

    def check(self, agent, session_id: str) -> BudgetStatus:
        config = {"configurable": {"thread_id": session_id}}
        try:
            state = agent.get_state(config)
            messages = state.values.get("messages", []) if state and state.values else []
        except Exception:
            messages = []

        msg_count = len(messages)
        total_chars = sum(len(str(getattr(m, "content", ""))) for m in messages)
        total_tokens = int(total_chars / CHARS_PER_TOKEN)
        should_warn = total_tokens >= self._warning
        should_compact = total_tokens >= self._compact

        prompt = ""
        if should_compact and messages:
            split = max(2, len(messages) - self._keep * 2)
            old = messages[:split]
            parts = []
            for m in old[-20:]:
                role = getattr(m, "type", "?")
                c = str(getattr(m, "content", ""))[:100]
                parts.append(f"[{role}]: {c}")
            prompt = (f"总结以下 {len(old)} 条历史消息为 200 字摘要:\n"
                      + "\n".join(parts))

        return BudgetStatus(
            total_tokens=total_tokens, message_count=msg_count,
            should_warn=should_warn, should_compact=should_compact,
            compact_prompt=prompt,
        )

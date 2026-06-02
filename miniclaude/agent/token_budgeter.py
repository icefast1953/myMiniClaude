"""Token Budgeter —— 监控 token 用量 + 自动压缩对话历史。

配合 SqliteSaver checkpoint 读取消息列表，估算 token 用量。
超过阈值时自动生成摘要，替换旧消息。
"""

from dataclasses import dataclass

from langchain_core.messages import AIMessage, HumanMessage

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
    """Token 预算管理器 —— 检测 + 执行 compact。"""

    def __init__(self, warning: int = WARNING_THRESHOLD,
                 compact: int = COMPACT_THRESHOLD,
                 keep: int = KEEP_RECENT):
        self._warning = warning
        self._compact = compact
        self._keep = keep

    def check(self, agent, session_id: str) -> BudgetStatus:
        """检查 token 预算状态。"""
        config = {"configurable": {"thread_id": session_id}}
        try:
            state = agent.get_state(config)
            messages = state.values.get("messages", []) if state and state.values else []
        except Exception:
            messages = []

        msg_count = len(messages)
        total_chars = sum(len(str(getattr(m, "content", ""))) for m in messages)
        total_tokens = int(total_chars / CHARS_PER_TOKEN)

        prompt = ""
        if total_tokens >= self._compact and messages:
            split = max(2, len(messages) - self._keep * 2)
            old = messages[:split]
            parts = []
            for m in old[-20:]:
                role = getattr(m, "type", "?")
                c = str(getattr(m, "content", ""))[:100]
                parts.append(f"[{role}]: {c}")
            prompt = (f"请用 200 字以内总结以下对话关键信息:\n" + "\n".join(parts))

        return BudgetStatus(
            total_tokens=total_tokens, message_count=msg_count,
            should_warn=total_tokens >= self._warning,
            should_compact=total_tokens >= self._compact,
            compact_prompt=prompt,
        )

    async def compact(self, agent, session_id: str, model) -> str:
        """执行压缩: 用 LLM 生成摘要 + update_state 替换旧消息。

        返回结果描述字符串。
        """
        config = {"configurable": {"thread_id": session_id}}
        try:
            state = agent.get_state(config)
            messages = list(state.values.get("messages", [])) if state and state.values else []
        except Exception:
            return "无法读取会话状态"

        if len(messages) <= self._keep * 2:
            return f"消息不足 ({len(messages)} 条)，无需压缩"

        # 分离旧消息和最近消息
        keep_count = self._keep * 2  # user + assistant 各一次 = 1轮
        old_msgs = messages[:-keep_count]
        recent_msgs = messages[-keep_count:]

        # 用 LLM 生成摘要
        parts = []
        for m in old_msgs[-30:]:  # 最多取最近30条旧消息做摘要
            role = "用户" if isinstance(m, HumanMessage) else "AI" if isinstance(m, AIMessage) else getattr(m, "type", "?")
            c = str(getattr(m, "content", ""))[:150]
            if c.strip():
                parts.append(f"[{role}]: {c}")

        summary_text = ""
        if parts:
            try:
                summary_msg = await model.ainvoke([
                    HumanMessage(content=(
                        f"请用 200 字以内总结以下对话的关键决策和背景信息，"
                        f"用于后续对话的上下文恢复:\n\n" + "\n".join(parts)
                    ))
                ])
                summary_text = f"[对话摘要] {str(summary_msg.content)}"
            except Exception:
                summary_text = f"[自动摘要] 前 {len(old_msgs)} 条消息已移除"

        # 用 summary + recent 替换全部消息
        new_messages = [AIMessage(content=summary_text)] + recent_msgs
        try:
            agent.update_state(config, values={"messages": new_messages})
        except Exception:
            pass  # 静默失败，不阻塞对话

        before_tokens = int(
            sum(len(str(getattr(m, "content", ""))) for m in old_msgs) / CHARS_PER_TOKEN
        )
        return (
            f"压缩完成: {len(old_msgs)} 条旧消息 → 1 条摘要 "
            f"(节省 ~{before_tokens} tokens，保留最近 {self._keep} 轮)"
        )

"""Token Budgeter —— 监控 token 用量 + 三级降级压缩。

配合 AsyncSqliteSaver checkpoint 读取消息列表，估算 token 用量。
超过阈值时执行分级压缩。
所有 state 访问均通过 async 接口（aget_state / aupdate_state）。
"""

from dataclasses import dataclass

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    ToolMessage,
)
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from miniclaude.agent.compressor import (
    L2L3Result,
    apply_l1,
    apply_l2_l3,
    estimate_tokens,
)

WARNING_THRESHOLD = 4000
COMPACT_THRESHOLD = 8000
KEEP_RECENT = 5


def _safe_split_point(messages: list[BaseMessage], min_keep: int) -> int:
    """找安全切分点——不会把 ToolMessage 和它的 tool_calls 拆开。

    从末尾往前找，确保拆分边界是 HumanMessage（新一轮对话开始），
    或者是一个不带 tool_calls 的 AIMessage。
    """
    if len(messages) <= min_keep:
        return 0

    split = len(messages) - min_keep
    # 往后扫描，保证不以孤立的 ToolMessage 开头
    for i in range(split, len(messages)):
        msg = messages[i]
        if isinstance(msg, HumanMessage):
            return i  # 安全：新一轮用户输入开始
        if isinstance(msg, AIMessage) and not (
            hasattr(msg, "tool_calls") and msg.tool_calls
        ):
            # 带 tool_calls 的 AIMessage 后面跟 ToolMessage，不能从这里切
            # 不带 tool_calls 的纯文本 AIMessage 是安全的切分点之后
            pass
        # ToolMessage 前面必须有 AIMessage.tool_calls，不能作为开头
    # 回退：从 split 点往前找最近的 HumanMessage
    for i in range(split, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return i
    return max(0, split)


@dataclass
class BudgetStatus:
    total_tokens: int
    message_count: int
    should_warn: bool
    should_compact: bool
    compact_prompt: str


class TokenBudgeter:
    """Token 预算管理器 —— 检测 + 分级压缩。"""

    def __init__(self, warning=WARNING_THRESHOLD,
                 compact=COMPACT_THRESHOLD, keep=KEEP_RECENT):
        self._warning = warning
        self._compact = compact
        self._keep = keep

    async def check(self, agent, session_id: str,
                    task_profile: dict | None = None) -> BudgetStatus:
        """检查 token 预算状态（async）。"""
        config = {"configurable": {"thread_id": session_id}}
        try:
            state = await agent.aget_state(config)
            messages = state.values.get("messages", []) if state and state.values else []
        except Exception:
            messages = []

        msg_count = len(messages)
        total_tokens = estimate_tokens(messages)

        warn_threshold = self._warning
        compact_threshold = self._compact
        if task_profile and task_profile.get("compression_policy"):
            policy = task_profile["compression_policy"]
            compact_threshold = policy.get("compact_threshold", self._compact)
            warn_threshold = policy.get("warning_threshold", int(compact_threshold * 0.8))

        prompt = ""
        if total_tokens >= compact_threshold and messages:
            prompt = f"Token 超限 (~{total_tokens}/{compact_threshold})，将执行分级压缩"

        return BudgetStatus(
            total_tokens=total_tokens, message_count=msg_count,
            should_warn=total_tokens >= warn_threshold,
            should_compact=total_tokens >= compact_threshold,
            compact_prompt=prompt,
        )

    async def compact(self, agent, session_id: str, model,
                      task_profile: dict | None = None) -> str:
        """执行分级压缩（async）。"""
        config = {"configurable": {"thread_id": session_id}}

        try:
            state = await agent.aget_state(config)
            messages = list(state.values.get("messages", [])) if state and state.values else []
        except Exception:
            return "无法读取会话状态"

        if len(messages) <= self._keep * 2:
            return f"消息不足 ({len(messages)} 条)，无需压缩"

        compact_threshold = self._compact
        keep_rounds = self._keep
        if task_profile and task_profile.get("compression_policy"):
            policy = task_profile["compression_policy"]
            compact_threshold = policy.get("compact_threshold", self._compact)
            keep_rounds = policy.get("keep_recent", self._keep)

        keep_count = keep_rounds * 2
        split = _safe_split_point(messages, keep_count)
        old_msgs = list(messages[:split])
        recent_msgs = list(messages[split:])
        old_tokens_before = estimate_tokens(old_msgs)

        # L1
        l1_msgs = apply_l1(old_msgs)
        l1_tokens = estimate_tokens(l1_msgs)
        l1_saved = old_tokens_before - l1_tokens

        if l1_tokens + estimate_tokens(recent_msgs) <= compact_threshold:
            new_messages = [RemoveMessage(id=REMOVE_ALL_MESSAGES), *l1_msgs, *recent_msgs]
            try:
                await agent.aupdate_state(config, values={"messages": new_messages})
            except Exception:
                pass
            return (f"L1 压缩完成: {len(old_msgs)} 条旧消息 → "
                    f"{len(l1_msgs)} 条 ToolSummary (节省 ~{l1_saved} tokens)")

        # L2+L3
        l2l3: L2L3Result = await apply_l2_l3(old_msgs, model)
        if l2l3.summary:
            l2_msg = AIMessage(content=f"[对话摘要] {l2l3.summary}")
            summary_msg = l2_msg
            chosen_level = "L2"
            l2_combined = estimate_tokens([l2_msg]) + estimate_tokens(recent_msgs)
        else:
            summary_msg = None
            chosen_level = ""
            l2_combined = float("inf")

        if l2_combined > compact_threshold and l2l3.state:
            summary_msg = AIMessage(content=l2l3.state)
            chosen_level = "L3"
        elif summary_msg is None:
            summary_msg = AIMessage(content=f"[自动摘要] 前 {len(old_msgs)} 条消息已移除")
            chosen_level = "fallback"

        new_messages = [RemoveMessage(id=REMOVE_ALL_MESSAGES), summary_msg, *recent_msgs]
        try:
            await agent.aupdate_state(config, values={"messages": new_messages})
        except Exception:
            pass

        new_tokens = estimate_tokens([summary_msg]) + estimate_tokens(recent_msgs)
        return (f"{chosen_level} 压缩完成: {len(old_msgs)} 条旧消息 → 1 条摘要 "
                f"(~{old_tokens_before} → ~{new_tokens} tokens, "
                f"L1 已节省 ~{l1_saved} tokens, 保留最近 {keep_rounds} 轮)")

"""Token Budgeter —— 监控 token 用量 + 三级降级压缩。

配合 SqliteSaver checkpoint 读取消息列表，估算 token 用量。
超过阈值时执行分级压缩：
  L1: 极简规则（统计+首尾片段，不调 LLM）
  L2: LLM 对话摘要（保留调查过程和结论）
  L3: LLM 状态声明（仅保留当前世界状态）
"""

from dataclasses import dataclass

from langchain_core.messages import AIMessage, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from miniclaude.agent.compressor import (
    CHARS_PER_TOKEN,
    L2L3Result,
    apply_l1,
    apply_l2_l3,
    estimate_tokens,
)

# ── 默认阈值 ──
# PR2 引入 TaskClassifier 后，这些阈值将按任务类型动态调整。
WARNING_THRESHOLD = 4000
COMPACT_THRESHOLD = 8000
KEEP_RECENT = 5  # 保留最近 N 轮（每轮 = user + assistant）


@dataclass
class BudgetStatus:
    total_tokens: int
    message_count: int
    should_warn: bool
    should_compact: bool
    compact_prompt: str


class TokenBudgeter:
    """Token 预算管理器 —— 检测 + 分级压缩。"""

    def __init__(
        self,
        warning: int = WARNING_THRESHOLD,
        compact: int = COMPACT_THRESHOLD,
        keep: int = KEEP_RECENT,
    ):
        self._warning = warning
        self._compact = compact
        self._keep = keep

    def check(
        self, agent, session_id: str, task_profile: dict | None = None
    ) -> BudgetStatus:
        """检查 token 预算状态。

        task_profile 暂未生效（PR2），reserved for adaptive thresholds。
        """
        config = {"configurable": {"thread_id": session_id}}
        try:
            state = agent.get_state(config)
            messages = (
                state.values.get("messages", []) if state and state.values else []
            )
        except Exception:
            messages = []

        msg_count = len(messages)
        total_tokens = estimate_tokens(messages)

        # PR2: 使用 task_profile 中的自适应阈值替换默认值
        warn_threshold = self._warning
        compact_threshold = self._compact
        if task_profile and task_profile.get("compression_policy"):
            policy = task_profile["compression_policy"]
            compact_threshold = policy.get("compact_threshold", self._compact)
            warn_threshold = policy.get(
                "warning_threshold", int(compact_threshold * 0.8)
            )

        prompt = ""
        if total_tokens >= compact_threshold and messages:
            prompt = f"Token 超限 (~{total_tokens}/{compact_threshold})，将执行分级压缩"

        return BudgetStatus(
            total_tokens=total_tokens,
            message_count=msg_count,
            should_warn=total_tokens >= warn_threshold,
            should_compact=total_tokens >= compact_threshold,
            compact_prompt=prompt,
        )

    async def compact(
        self,
        agent,
        session_id: str,
        model,
        task_profile: dict | None = None,
    ) -> str:
        """执行分级压缩。

        降级循环：
          1. 分离旧消息 vs 最近 N 轮
          2. L1（规则）→ 估算 → 回到安全区? 停
          3. L2+L3（一次 LLM）→ L2 估算 → 够用? 用 L2
          4. L2 不够 → 降级到 L3 状态声明
          5. update_state(REMOVE_ALL + 新消息)

        返回日志描述。
        """
        config = {"configurable": {"thread_id": session_id}}

        # ── 读取消息 ──
        try:
            state = agent.get_state(config)
            messages = list(state.values.get("messages", [])) if state and state.values else []
        except Exception:
            return "无法读取会话状态"

        if len(messages) <= self._keep * 2:
            return f"消息不足 ({len(messages)} 条)，无需压缩"

        # 使用自适应阈值
        compact_threshold = self._compact
        keep_rounds = self._keep
        if task_profile and task_profile.get("compression_policy"):
            policy = task_profile["compression_policy"]
            compact_threshold = policy.get("compact_threshold", self._compact)
            keep_rounds = policy.get("keep_recent", self._keep)

        keep_count = keep_rounds * 2
        old_msgs = list(messages[:-keep_count])
        recent_msgs = list(messages[-keep_count:])

        old_tokens_before = estimate_tokens(old_msgs)

        # ── Level 1: 极简规则压缩（不调 LLM）──
        l1_msgs = apply_l1(old_msgs)
        l1_tokens = estimate_tokens(l1_msgs)
        l1_saved = old_tokens_before - l1_tokens

        # L1 + recent 是否已回到安全区？
        l1_combined_tokens = l1_tokens + estimate_tokens(recent_msgs)
        if l1_combined_tokens <= compact_threshold:
            # L1 就够了
            new_messages = [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *l1_msgs,
                *recent_msgs,
            ]
            try:
                agent.update_state(config, values={"messages": new_messages})
            except Exception:
                pass
            return (
                f"L1 压缩完成: {len(old_msgs)} 条旧消息 → "
                f"{len(l1_msgs)} 条 ToolSummary "
                f"(节省 ~{l1_saved} tokens，回到安全区)"
            )

        # ── Level 2+3: LLM 双输出 ──
        l2l3: L2L3Result = await apply_l2_l3(old_msgs, model)

        # 尝试 Level 2（对话摘要）
        if l2l3.summary:
            l2_msg = AIMessage(content=f"[对话摘要] {l2l3.summary}")
            l2_combined = estimate_tokens([l2_msg]) + estimate_tokens(recent_msgs)
            chosen_level = "L2"
            summary_msg = l2_msg
        else:
            l2_combined = float("inf")
            chosen_level = ""
            summary_msg = None

        # Level 2 不够 → 降级到 Level 3
        if l2_combined > compact_threshold and l2l3.state:
            l3_msg = AIMessage(content=l2l3.state)
            chosen_level = "L3"
            summary_msg = l3_msg
        elif summary_msg is None:
            # 都没有产出，fallback
            fallback = f"[自动摘要] 前 {len(old_msgs)} 条消息已移除"
            summary_msg = AIMessage(content=fallback)
            chosen_level = "fallback"

        # ── 写入 state ──
        new_messages = [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            summary_msg,
            *recent_msgs,
        ]
        try:
            agent.update_state(config, values={"messages": new_messages})
        except Exception:
            pass  # 静默失败

        new_tokens = estimate_tokens([summary_msg]) + estimate_tokens(recent_msgs)
        return (
            f"{chosen_level} 压缩完成: {len(old_msgs)} 条旧消息 → 1 条摘要 "
            f"(~{old_tokens_before} → ~{new_tokens} tokens，"
            f"L1 已节省 ~{l1_saved} tokens，保留最近 {keep_rounds} 轮)"
        )

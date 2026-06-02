"""消息压缩器 —— 三级降级策略。

L1: 极简规则（不调 LLM）—— 统一格式提取 stats + 首尾片段。
L2: LLM 对话摘要 —— 保留调查过程和结论。
L3: LLM 状态声明 —— 仅保留当前世界状态的 YAML。

compact() 内部降级循环：
  apply_l1() → 估算 token → 回到安全区? 停
  apply_l2_l3() → 一次 LLM 双输出 → 估算 token → 选 L2 或 L3 → apply
"""

import hashlib
from dataclasses import dataclass, field

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

# ── 常量 ──

CHARS_PER_TOKEN = 3.5
HEAD_LINES = 10
TAIL_LINES = 10
MAX_TOOL_CHARS_FOR_PASSTHROUGH = 500  # 小于此字符数的 ToolMessage 不压缩


# ── 数据结构 ──


@dataclass
class CompressResult:
    """压缩结果。"""

    messages: list[BaseMessage]
    stats: dict = field(default_factory=dict)


# ── Token 估算 ──


def estimate_tokens(messages: list[BaseMessage]) -> int:
    """估算消息列表的总 token 数。"""
    total = 0
    for m in messages:
        c = str(getattr(m, "content", ""))
        total += len(c)
    return int(total / CHARS_PER_TOKEN)


# ── Level 1: 极简规则 ──


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _compress_tool_message(msg: ToolMessage) -> str:
    """对单个 ToolMessage 做 Level 1 压缩。

    统一格式，不区分工具类型：
      - 保留工具名、字符数、行数、hash
      - 保留首 10 行 + 尾 10 行作为检索锚点
      - 小输出（<500 字符）不压缩，原样保留
    """
    content = str(msg.content)
    if len(content) <= MAX_TOOL_CHARS_FOR_PASSTHROUGH:
        return content

    lines = content.split("\n")
    head = "\n".join(lines[:HEAD_LINES])
    tail = "\n".join(lines[-TAIL_LINES:]) if len(lines) > HEAD_LINES else ""

    parts = [
        f"[ToolResult] {msg.name}",
        f"chars: {len(content)}",
        f"lines: {len(lines)}",
        f"sha256: {_hash(content)}",
    ]
    if head:
        parts.append(f"--- head ({HEAD_LINES} lines) ---\n{head}")
    if tail:
        parts.append(f"--- tail ({TAIL_LINES} lines) ---\n{tail}")

    return "\n".join(parts)


def apply_l1(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Level 1: 对所有 ToolMessage 做极简规则压缩。

    不调 LLM，纯程序完成。
    对 HumanMessage/AIMessage/SystemMessage 原样保留。
    """
    result: list[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            compressed = _compress_tool_message(msg)
            result.append(ToolMessage(
                content=compressed,
                tool_call_id=getattr(msg, "tool_call_id", ""),
                name=getattr(msg, "name", "unknown"),
            ))
        else:
            result.append(msg)
    return result


# ── Level 2+3: LLM 双输出 ──


L2_L3_PROMPT = """请对以下对话历史进行两级压缩，用于在上下文窗口不足时保留关键信息。

## 第一部分：CONVERSATION_SUMMARY（200 字以内）
保留对话的调查过程、关键决策和结论。这用于"还需要继续开发/调试"的场景。

## 第二部分：STATE_DECLARATION（YAML 格式）
仅保留当前世界状态，丢弃所有推理过程。这用于"只关心现在在哪、要做什么"的场景。

```yaml
goal: [当前任务目标]
current_status: [一句话描述当前进度]
known_facts:
  - [已确认的事实]
completed:
  - [已完成的关键步骤]
pending:
  - [待完成的事项]
```

## 对话历史

{history}

---

请严格按照以下格式输出（用 --- 分隔两部分）：

CONVERSATION_SUMMARY
<摘要文本>

---
STATE_DECLARATION
```yaml
<YAML>
```"""


@dataclass
class L2L3Result:
    summary: str  # Level 2: 对话摘要
    state: str    # Level 3: 状态声明


def parse_l2_l3_response(text: str) -> L2L3Result:
    """解析 LLM 双输出响应。"""
    summary = ""
    state = ""

    # 尝试按分隔符拆分
    if "CONVERSATION_SUMMARY" in text and "STATE_DECLARATION" in text:
        # 找到两部分
        parts = text.split("STATE_DECLARATION", 1)
        summary_part = parts[0].replace("CONVERSATION_SUMMARY", "").strip()
        state_part = parts[1].strip()

        # 清理 summary
        summary = summary_part.strip()

        # 提取 YAML（可能被 ```yaml ... ``` 包裹）
        if "```" in state_part:
            yaml_start = state_part.find("```")
            yaml_end = state_part.find("```", yaml_start + 3)
            if yaml_end > yaml_start:
                state = state_part[yaml_start:yaml_end + 3]
            else:
                state = state_part
        else:
            state = state_part
    else:
        # LLM 没有严格按格式输出，整个文本作为 summary
        summary = text

    return L2L3Result(summary=summary.strip(), state=state.strip())


async def apply_l2_l3(
    messages: list[BaseMessage],
    model,
    max_input_messages: int = 30,
) -> L2L3Result:
    """Level 2+3: 一次 LLM 调用，产出对话摘要 + 状态声明。

    取最近 max_input_messages 条消息作为 LLM 输入。
    """
    # 构建输入：截取消息摘要
    parts: list[str] = []
    for m in messages[-max_input_messages:]:
        role = _role_label(m)
        c = str(getattr(m, "content", ""))[:200]
        if c.strip():
            parts.append(f"[{role}]: {c}")

    if not parts:
        return L2L3Result(summary="", state="")

    prompt = L2_L3_PROMPT.format(history="\n".join(parts))

    try:
        response = await model.ainvoke([HumanMessage(content=prompt)])
        return parse_l2_l3_response(str(response.content))
    except Exception:
        return L2L3Result(
            summary=f"[自动摘要] 前 {len(messages)} 条消息",
            state="",
        )


# ── 辅助 ──


def _role_label(msg: BaseMessage) -> str:
    if isinstance(msg, HumanMessage):
        return "用户"
    if isinstance(msg, AIMessage):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            names = [tc.get("name", "?") if isinstance(tc, dict) else getattr(tc, "name", "?")
                     for tc in msg.tool_calls]
            return f"AI(调用 {', '.join(names)})"
        return "AI"
    if isinstance(msg, ToolMessage):
        return f"工具({getattr(msg, 'name', '?')})"
    if isinstance(msg, SystemMessage):
        return "系统"
    return getattr(msg, "type", "?")


def _summarize_for_l2(messages: list[BaseMessage], max_chars: int = 3000) -> str:
    """将消息列表转为精简文本，供 compact 日志使用。"""
    parts = []
    total = 0
    for m in messages:
        c = str(getattr(m, "content", ""))[:150]
        if c.strip():
            role = _role_label(m)
            line = f"[{role}]: {c}"
            total += len(line)
            if total > max_chars:
                parts.append("...(已截断)")
                break
            parts.append(line)
    return "\n".join(parts)

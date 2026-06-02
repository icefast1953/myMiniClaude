"""TaskClassifier —— 四层任务分类器。

Layer 1: 显式模式     — 用户通过 /mode 指定，最高优先级
Layer 2: 意图分类     — 规则先行 + LLM 兜底
Layer 3: 上下文补偿   — 最近 N 轮工具行为分析
Layer 4: 阶段识别     — 状态机：探索→设计→实现→调试→验证→收尾

输出 TaskProfile，驱动自适应 Token 压缩阈值。
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage


class TaskType(str, Enum):
    CODE_GEN = "code-gen"
    DEBUG = "debug"
    EXPLAIN = "explain"
    REFACTOR = "refactor"
    TEST = "test"
    ENV = "env"
    UNKNOWN = "unknown"


class Stage(str, Enum):
    EXPLORING = "exploring"
    DESIGNING = "designing"
    IMPLEMENTING = "implementing"
    DEBUGGING = "debugging"
    VERIFYING = "verifying"
    CLOSING = "closing"


# ── 自适应阈值映射表 ──

COMPRESSION_POLICIES: dict[TaskType, dict] = {
    TaskType.CODE_GEN: {
        "compact_threshold": 16000, "warning_threshold": 12800,
        "keep_recent": 3, "prefer_level": "L3",
        "description": "code-gen: 目标明确，激进压缩",
    },
    TaskType.DEBUG: {
        "compact_threshold": 64000, "warning_threshold": 51200,
        "keep_recent": 8, "prefer_level": "L1",
        "description": "debug: 保留最多上下文，尽量不丢细节",
    },
    TaskType.EXPLAIN: {
        "compact_threshold": 24000, "warning_threshold": 19200,
        "keep_recent": 5, "prefer_level": "L2",
        "description": "explain: 适中",
    },
    TaskType.REFACTOR: {
        "compact_threshold": 32000, "warning_threshold": 25600,
        "keep_recent": 6, "prefer_level": "L2",
        "description": "refactor: 保留结构约束",
    },
    TaskType.TEST: {
        "compact_threshold": 24000, "warning_threshold": 19200,
        "keep_recent": 5, "prefer_level": "L2",
        "description": "test: 兼顾准确性和可读性",
    },
    TaskType.ENV: {
        "compact_threshold": 64000, "warning_threshold": 51200,
        "keep_recent": 10, "prefer_level": "L1",
        "description": "env: 最吃细节，压缩最保守",
    },
    TaskType.UNKNOWN: {
        "compact_threshold": 32000, "warning_threshold": 25600,
        "keep_recent": 5, "prefer_level": "L2",
        "description": "default",
    },
}

# ── Hysteresis ──
HYSTERESIS_WINDOW = 3
STAGE_HYST_WINDOW = 2


@dataclass
class TaskProfile:
    task_type: TaskType = TaskType.UNKNOWN
    confidence: float = 0.0
    stage: Stage = Stage.EXPLORING
    stage_confidence: float = 0.0
    compression_policy: dict = field(default_factory=dict)
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type.value,
            "confidence": self.confidence,
            "stage": self.stage.value,
            "stage_confidence": self.stage_confidence,
            "compression_policy": self.compression_policy,
            "source": self.source,
        }


# ── Layer 2: 意图分类规则 ──
# 每个 pattern 是一组正则关键词，命中后按 confidence 比较，取最高分。

INTENT_RULES: list[tuple[str, TaskType, float]] = [
    (
        r"报错|错误|bug|异常|fix|debug|traceback|stack ?trace|exception"
        r"|出错|挂了|不行了|还是不行|仍然|再查|再试|不对了"
        r"|失败$|失败了|老是失败|同样的错|跑不起来"
        r"|没反应|没有.*反应|怪怪的|有问题|不对劲|怎么回事",
        TaskType.DEBUG, 0.85,
    ),
    (
        r"重构|refactor|rename|extract|抽[取离]|提取|重命名|整理"
        r"|拆分?一下|优化.*结构|统一|去重|拆[分拆]|精简",
        TaskType.REFACTOR, 0.80,
    ),
    (
        r"测试|test|assert|mock|pytest|unittest|覆盖率|coverage"
        r"|验证.*对不|边界|对不对",
        TaskType.TEST, 0.80,
    ),
    (
        r"解释|说明一下|干嘛的|是什么|explain|什么意思"
        r"|为什么.*写|理一下.*逻辑|看不懂|帮我理解|设计思路|思路是什么",
        TaskType.EXPLAIN, 0.75,
    ),
    (
        r"pip.*错|npm.*错|pip.*失败|npm.*失败|装不上|安装.*失败"
        r"|依赖.*不上|虚拟环境|环境.*问题|配置.*环境"
        r"|^env$|版本.*升级|升级.*版本",
        TaskType.ENV, 0.90,
    ),
    (
        r"安装|^pip\s|npm\s|setup\s|pip3?\s",
        TaskType.ENV, 0.80,
    ),
    (
        r"写\s|写一|生成|实现|开发|添加.*功能|新建|创建"
        r"|帮我做|给我写|generate|create|搭建|搭.*骨架"
        r"|补全.*TODO|需要一个.*模块|缺少.*模块",
        TaskType.CODE_GEN, 0.70,
    ),
]


def classify_intent_rules(text: str) -> tuple[TaskType, float]:
    """Layer 2 规则匹配。"""
    best_type = TaskType.UNKNOWN
    best_conf = 0.0
    for pattern, task_type, confidence in INTENT_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            if confidence > best_conf:
                best_conf = confidence
                best_type = task_type
    return best_type, best_conf


# ── Layer 3 & 4: 上下文分析 ──


def _extract_tool_events(messages: list[BaseMessage], n_rounds: int = 8) -> list[dict]:
    events: list[dict] = []
    for msg in messages[-n_rounds * 2:]:
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                events.append({"type": "tool_call", "tool": name})
        elif isinstance(msg, ToolMessage):
            content = str(getattr(msg, "content", ""))
            is_error = any(kw in content.lower() for kw in
                          ["traceback", "error", "exception", "failed", "fail"])
            events.append({
                "type": "tool_result",
                "tool": getattr(msg, "name", "?"),
                "is_error": is_error,
            })
        elif isinstance(msg, HumanMessage):
            content = str(msg.content).lower()
            is_fix_request = any(kw in content for kw in
                                ["still", "again", "retry", "not working",
                                 "wrong", "incorrect", "doesn't work"])
            events.append({"type": "user_msg", "is_fix_request": is_fix_request})
    return events


def analyze_context(events: list[dict]) -> tuple[TaskType, float]:
    scores: dict[TaskType, float] = {t: 0.0 for t in TaskType}
    tool_names = [e.get("tool", "") for e in events if e["type"] == "tool_call"]
    error_count = sum(1 for e in events if e.get("is_error"))
    fix_requests = sum(1 for e in events if e.get("is_fix_request"))
    total_tool_calls = len(tool_names) or 1

    read_ratio = sum(1 for n in tool_names if n in ("read", "grep", "glob")) / total_tool_calls
    write_ratio = sum(1 for n in tool_names if n in ("write", "edit")) / total_tool_calls
    bash_ratio = sum(1 for n in tool_names if n == "bash") / total_tool_calls

    if read_ratio > 0.6:
        scores[TaskType.EXPLAIN] += 2
    if write_ratio > 0.4:
        scores[TaskType.CODE_GEN] += 2
        scores[TaskType.REFACTOR] += 1
    if error_count >= 3 or fix_requests >= 1:
        scores[TaskType.DEBUG] += 3
    if error_count >= 1:
        scores[TaskType.DEBUG] += 1
    if bash_ratio > 0.3:
        scores[TaskType.TEST] += 1
        scores[TaskType.ENV] += 1

    best = max(scores, key=scores.get)
    best_score = scores[best]
    if best_score <= 0:
        return TaskType.UNKNOWN, 0.0
    total = sum(scores.values()) or 1
    return best, min(best_score / max(total, 1), 0.95)


def identify_stage(events: list[dict], current_stage: Stage) -> tuple[Stage, float]:
    tool_names = [e.get("tool", "") for e in events if e["type"] == "tool_call"]
    if not tool_names:
        return Stage.DESIGNING, 0.60

    total = len(tool_names)
    error_count = sum(1 for e in events if e.get("is_error"))
    fix_requests = sum(1 for e in events if e.get("is_fix_request"))

    read_ratio = sum(1 for n in tool_names if n in ("read", "grep", "glob")) / total
    write_ratio = sum(1 for n in tool_names if n in ("write", "edit")) / total
    bash_ratio = sum(1 for n in tool_names if n == "bash") / total

    if error_count >= 2 or fix_requests >= 1:
        return Stage.DEBUGGING, 0.85
    if bash_ratio > 0.4 and error_count == 0:
        return Stage.VERIFYING, 0.80
    if write_ratio > 0.5:
        return Stage.IMPLEMENTING, 0.80
    if read_ratio > 0.7:
        return Stage.EXPLORING, 0.85
    return current_stage, 0.50


# ── TaskClassifier ──


class TaskClassifier:
    """四层任务分类器。"""

    def __init__(self):
        self._explicit_mode: TaskType | None = None

    def set_mode(self, mode: TaskType | str | None):
        if mode is None:
            self._explicit_mode = None
        elif isinstance(mode, str):
            try:
                self._explicit_mode = TaskType(mode)
            except ValueError:
                self._explicit_mode = None
        else:
            self._explicit_mode = mode

    @property
    def explicit_mode(self) -> TaskType | None:
        return self._explicit_mode

    async def profile(self, user_input: str, agent, session_id: str) -> TaskProfile:
        config = {"configurable": {"thread_id": session_id}}
        try:
            state = await agent.aget_state(config)
            messages = list(state.values.get("messages", [])) if state and state.values else []
            prev_context = state.values.get("task_context", {}) if state and state.values else {}
        except Exception:
            messages = []
            prev_context = {}

        prev_history: list[str] = prev_context.get("task_history", [])
        prev_stage_history: list[str] = prev_context.get("stage_history", [])

        # L1: explicit
        if self._explicit_mode is not None:
            profile = TaskProfile(
                task_type=self._explicit_mode, confidence=1.0,
                compression_policy=COMPRESSION_POLICIES.get(
                    self._explicit_mode, COMPRESSION_POLICIES[TaskType.UNKNOWN]),
                source="L1:explicit",
            )
            profile.stage = self._derive_stage_from_type(self._explicit_mode)
            await self._write_task_context(agent, config, profile, prev_history, prev_stage_history)
            return profile

        # L2: intent rules
        l2_type, l2_conf = classify_intent_rules(user_input)
        # L3: context
        events = _extract_tool_events(messages)
        l3_type, l3_conf = analyze_context(events)
        # L4: stage
        current_stage = Stage.EXPLORING
        if prev_stage_history:
            try:
                current_stage = Stage(prev_stage_history[-1])
            except ValueError:
                pass
        stage, stage_conf = identify_stage(events, current_stage)

        # Conflict: L3 > L2
        if l3_conf > 0.7 and l3_type != TaskType.UNKNOWN:
            task_type, confidence, source = l3_type, l3_conf, "L3:context"
        elif l2_conf > 0.6:
            task_type, confidence, source = l2_type, l2_conf, "L2:intent"
        else:
            task_type, confidence, source = TaskType.UNKNOWN, 0.3, "L2:fallback"

        task_type = self._apply_hysteresis(task_type, prev_history, HYSTERESIS_WINDOW)
        stage = self._apply_stage_hysteresis(stage, prev_stage_history, STAGE_HYST_WINDOW)

        policy = COMPRESSION_POLICIES.get(task_type, COMPRESSION_POLICIES[TaskType.UNKNOWN])
        profile = TaskProfile(
            task_type=task_type, confidence=confidence,
            stage=stage, stage_confidence=stage_conf,
            compression_policy=policy, source=source,
        )
        await self._write_task_context(agent, config, profile, prev_history, prev_stage_history)
        return profile

    @staticmethod
    def _derive_stage_from_type(task_type: TaskType) -> Stage:
        if task_type == TaskType.DEBUG:
            return Stage.DEBUGGING
        if task_type == TaskType.TEST:
            return Stage.VERIFYING
        if task_type in (TaskType.CODE_GEN, TaskType.REFACTOR):
            return Stage.IMPLEMENTING
        return Stage.EXPLORING

    @staticmethod
    def _apply_hysteresis(new_type: TaskType, history: list[str], window: int) -> TaskType:
        history.append(new_type.value)
        if len(history) < window:
            return TaskType(Counter(history).most_common(1)[0][0])
        recent = history[-window:]
        if len(set(recent)) == 1:
            return TaskType(recent[0])
        return TaskType(Counter(recent).most_common(1)[0][0])

    @staticmethod
    def _apply_stage_hysteresis(new_stage: Stage, history: list[str], window: int) -> Stage:
        history.append(new_stage.value)
        if len(history) < window:
            return new_stage
        recent = history[-window:]
        if len(set(recent)) == 1:
            return Stage(recent[0])
        return new_stage

    @staticmethod
    async def _write_task_context(agent, config, profile, task_history, stage_history):
        try:
            await agent.aupdate_state(config, values={
                "task_context": {
                    "profile": profile.to_dict(),
                    "task_history": task_history[-20:],
                    "stage_history": stage_history[-20:],
                    "recent_events": [],
                }
            })
        except Exception:
            pass

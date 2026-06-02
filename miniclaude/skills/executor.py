"""Skill 执行器 —— inject（注入上下文）或 subagent（独立子代理）。"""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from miniclaude.agent.system_prompt import build_context_message
from miniclaude.skills.registry import Skill


def inject_context(skill: Skill, user_input: str, working_dir: str) -> HumanMessage:
    """上下文注入：skill body 前置到用户消息。"""
    ctx = build_context_message(working_dir)
    full = (
        f"[Skill: {skill.name}] {skill.description}\n\n"
        f"{skill.body}\n\n"
        f"---\n"
        f"{ctx}\n\n"
        f"用户请求: {user_input}"
    )
    return HumanMessage(content=full)


async def run_subagent(
    skill: Skill, user_input: str, working_dir: str, subagent_runner,
) -> str:
    """子代理模式。subagent_runner 负责工具过滤和模型选择。"""
    prompt = (
        f"[任务] {skill.description}\n\n{skill.body}\n\n"
        f"---\n{build_context_message(working_dir)}\n\n"
        f"用户请求: {user_input}"
    )
    try:
        return await subagent_runner.run(prompt, skill.tools, skill.model or None)
    except Exception as e:
        return f"Skill '{skill.name}' 执行失败: {e}"


async def execute(
    skill: Skill, user_input: str, working_dir: str,
    agent_loop, session_id: str, subagent_runner=None,
):
    """统一入口。返回 (result_text, injected_msg)。

    inject → (None, HumanMessage)，由调用方传入 run_stream()
    subagent → (result_text, None)
    """
    if skill.skill_type == "subagent" and subagent_runner:
        return (await run_subagent(skill, user_input, working_dir, subagent_runner), None)
    return (None, inject_context(skill, user_input, working_dir))

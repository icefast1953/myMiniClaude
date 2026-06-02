"""miniClaude 入口 —— REPL 循环 + 会话管理 + 长期记忆。"""

import asyncio
import os
import sys

from miniclaude.agent.agent_loop import AgentLoop
from miniclaude.agent.subagent import SubagentRunner
from miniclaude.agent.compressor import estimate_tokens
from miniclaude.agent.task_classifier import TaskClassifier, TaskType
from miniclaude.agent.token_budgeter import TokenBudgeter
from miniclaude.cli.rich_console import RichConsole
from miniclaude.config.app_config import Config
from miniclaude.llm.model_factory import create_model
from miniclaude.mcp.client import MCPClient
from miniclaude.mcp.tool_adapter import adapt_mcp_tools
from miniclaude.memory.memory_manager import MemoryManager
from miniclaude.memory.memory_tools import (
    set_memory_manager, tool_memory_forget,
    tool_memory_recall, tool_memory_save,
)
from miniclaude.storage.session_store import SessionStore
from miniclaude.tools.permission import PermissionManager, wrap_tool_with_permission
from miniclaude.tools.tool_bash import create_tool_bash
from miniclaude.tools.tool_task import setup_task_tool
from miniclaude.tools.tool_edit import tool_edit
from miniclaude.tools.tool_glob import tool_glob
from miniclaude.tools.tool_grep import tool_grep
from miniclaude.tools.tool_read import tool_read
from miniclaude.tools.tool_todo_write import tool_todo_write
from miniclaude.tools.tool_web_fetch import tool_web_fetch
from miniclaude.tools.tool_write import tool_write

HELP_TEXT = """[bold]命令:[/]
  /exit /help /clear /model
  /sessions  会话列表
  /new       新会话
  /switch ID 切换会话
  /memory    长期记忆
  /compact   Token 预算
  /token     Token 消耗统计
  /mode TYPE 任务模式 (debug/code-gen/test/refactor/explain/env/auto)
  /allow PAT 权限规则"""


async def main() -> None:
    config = Config.load()
    if not config.llm_api_key:
        print("错误: 未设置 DEEPSEEK_API_KEY"); return

    console = RichConsole()
    console.print_welcome()

    try:
        model = create_model(config)
    except Exception as e:
        console.print_error(f"模型初始化失败: {e}"); return

    # ── 会话存储 + SqliteSaver ──
    db_path = os.path.join(os.getcwd(), "miniclaude.db")
    sessions = SessionStore(db_path)
    await sessions.async_init()
    session_id = sessions.create("新会话")
    is_first = True
    console.print_system(f"[dim]会话: {session_id[:20]}...[/dim]")

    # ── 长期记忆 ──
    memory = MemoryManager(os.path.join(os.getcwd(), "memory"))
    set_memory_manager(memory)

    # ── 任务分类 + Token 预算 ──
    classifier = TaskClassifier()
    budgeter = TokenBudgeter()

    # ── MCP ──
    mcp_client = MCPClient("mcp.json", console._console)
    mcp_client.parse_servers()
    mcp_tools = []
    if mcp_client._servers:
        console.print_system("[dim]连接 MCP...[/dim]")
        await mcp_client.connect_all()
        mcp_tools = adapt_mcp_tools(mcp_client.get_all_tools())

    # ── 权限 ──
    perm = PermissionManager()

    # ── 工具 ──
    wd = os.getcwd()
    raw = [tool_read, tool_write, tool_edit, create_tool_bash(wd),
           tool_grep, tool_glob, tool_web_fetch, tool_todo_write,
           tool_memory_save, tool_memory_recall, tool_memory_forget]
    raw.append(setup_task_tool(SubagentRunner(model, raw), wd))
    raw.extend(mcp_tools)
    tools = [wrap_tool_with_permission(t, perm, _ask(console)) for t in raw]

    # ── Agent ──
    agent = AgentLoop(model, tools, sessions.checkpointer, memory, config)

    # ── REPL ──
    turns = 0
    while True:
        try:
            user_input = _read()
            if not user_input.strip(): continue

            if user_input.startswith("/"):
                sid, is_first, turns = _cmd(
                    user_input, console, perm, sessions, memory,
                    session_id, budgeter, agent, is_first, turns)
                if sid == "EXIT": break
                if sid != session_id:
                    session_id = sid
                    turns = 0
                continue

            console.print_user(user_input)
            console.show_thinking()

            # ── 任务分类 ──
            task_profile = classifier.profile(user_input, agent._agent, session_id)

            # Token 预算检查 + 自动压缩（自适应阈值）
            st = budgeter.check(agent._agent, session_id, task_profile.to_dict())
            if st.should_compact:
                mode_tag = f"[{task_profile.task_type.value}] " if task_profile.task_type != TaskType.UNKNOWN else ""
                console.print_system(
                    f"[dim]{mode_tag}Token 超限 (~{st.total_tokens})，自适应压缩...[/dim]")
                result = await budgeter.compact(
                    agent._agent, session_id, model, task_profile.to_dict())
                console.print_system(f"[dim]{result}[/dim]")
            elif st.should_warn:
                source = task_profile.source.split(":")[0] if task_profile.source else ""
                console.print_system(
                    f"[dim]Token: ~{st.total_tokens} ({st.message_count}条)"
                    f" | {task_profile.task_type.value}({source})[/dim]")

            final = await agent.run_stream(
                user_input, session_id=session_id,
                working_dir=wd, is_first=is_first,
                on_text=_on_text(console),
                on_tool_start=_on_tool_start(console),
                on_tool_end=_on_tool_end(console),
            )
            is_first = False
            turns += 1
            sessions.update(session_id, turns)

            console.hide_thinking(); console.finish_assistant()
            if final and console._renderer.buffer == "":
                console._console.print(final)

        except KeyboardInterrupt:
            console.hide_thinking(); console.finish_assistant()
            console.print_system("[dim]已中断[/dim]"); continue
        except EOFError:
            console.print_system("再见！"); break
        except Exception as e:
            console.hide_thinking()
            console.print_error(f"运行出错: {e}"); continue


# ── 回调 ──

def _ask(console: RichConsole):
    def h(name, key, args, reason):
        console.hide_thinking()
        console._console.print(f"\n  [bold yellow]🔒 {reason}[/] [dim]{name}[/]")
        from rich.prompt import Prompt
        c = Prompt.ask("  [y=一次/a=记住/n=拒绝]", choices=["y","a","n"], default="n")
        console._console.print()
        console.show_thinking()
        if c == "a": return True
        if c == "y": return None
        return False
    return h

def _on_text(c): return lambda t: (c.hide_thinking(), c.render_stream(t))
def _on_tool_start(c): return lambda n, a: (c.hide_thinking(), c.show_tool_call(n, a))
def _on_tool_end(c): return lambda n, o: c.show_tool_result(n, o)

def _read() -> str:
    from rich.prompt import Prompt
    return Prompt.ask("")


# ── 命令 ──

def _cmd(cmd, console, perm, sessions, memory, sid,
         budgeter, agent, is_first, turns):
    cmd = cmd.strip().lower(); p = cmd.split(None, 1)

    if cmd == "/exit":
        console.print_system("再见！"); return ("EXIT", is_first, turns)
    elif cmd == "/help":
        console._console.print(HELP_TEXT)
    elif cmd == "/clear":
        os.system("cls" if os.name == "nt" else "clear")
    elif cmd == "/model":
        c = Config.load()
        console.print_system(f"{c.llm_model} | {c.llm_base_url} | max_turns={c.max_turns}")
    elif cmd == "/sessions":
        sl = sessions.list(10)
        for s in sl:
            mk = " ←" if s["id"] == sid else ""
            console._console.print(f"  {s['id'][:22]} {s['title']}({s['turn_count']}轮){mk}")
    elif cmd == "/new":
        sid = sessions.create()
        console.print_system(f"新会话: {sid[:20]}...")
        return (sid, True, 0)
    elif cmd.startswith("/switch") and len(p) > 1:
        prefix = p[1]
        matched = [s for s in sessions.list(50) if s["id"].startswith(prefix)]
        if matched:
            sid = matched[0]["id"]
            console.print_system(f"切换到: {sid[:20]}...")
            return (sid, False, matched[0]["turn_count"])
        console.print_system("未找到")
    elif cmd == "/memory":
        idx = memory.get_index()
        if idx:
            console._console.print(f"[bold]长期记忆({len(memory.list_all())}条):[/]\n{idx}")
        else:
            console.print_system("暂无")
    elif cmd.startswith("/mode") and len(p) > 1:
        mode_str = p[1].strip().lower()
        if mode_str == "auto":
            classifier.set_mode(None)
            console.print_system("模式: 自动")
        else:
            try:
                classifier.set_mode(TaskType(mode_str))
                policy = classifier.profile("", agent._agent, sid).compression_policy
                console.print_system(
                    f"模式: {mode_str} | "
                    f"compact={policy.get('compact_threshold')} "
                    f"keep={policy.get('keep_recent')}轮")
            except ValueError:
                valid = ", ".join(t.value for t in TaskType)
                console.print_system(f"无效模式。可用: {valid}")
    elif cmd.startswith("/allow") and len(p) > 1:
        perm.add_rule(p[1], "allow")
        console.print_system(f"规则: {p[1]} → allow")
    elif cmd == "/token":
        try:
            state = agent._agent.get_state(
                {"configurable": {"thread_id": sid}})
            msgs = state.values.get("messages", []) if state and state.values else []
            from collections import Counter
            type_counts = Counter()
            type_tokens = Counter()
            for m in msgs:
                t = type(m).__name__
                type_counts[t] += 1
                type_tokens[t] += len(str(getattr(m, "content", "")))
            total = int(sum(type_tokens.values()) / 3.5)
            console._console.print(
                f"[bold]Token ({len(msgs)}条消息):[/]  ~{total} tokens")
            for t, n in type_counts.most_common():
                tk = int(type_tokens[t] / 3.5)
                console._console.print(f"  {t}: {n}条, ~{tk} tokens")
        except Exception as e:
            console.print_system(f"无法读取: {e}")
    elif cmd == "/compact":
        try:
            state = agent._agent.get_state(
                {"configurable": {"thread_id": sid}})
            msgs = state.values.get("messages", []) if state and state.values else []
            total_tokens = estimate_tokens(msgs)
            console._console.print(
                f"Token: ~{total_tokens} | {len(msgs)}条消息 | "
                f"compact 阈值={budgeter._compact}")
        except Exception:
            console.print_system("无法读取会话状态")
    else:
        console.print_system(f"未知: {cmd}")
    return (sid, is_first, turns)


# ── TUI ──

def main_tui() -> None:
    config = Config.load()
    if not config.llm_api_key:
        print("错误: 未设置 DEEPSEEK_API_KEY"); return
    model = create_model(config)
    wd = os.getcwd()
    memory = MemoryManager(os.path.join(wd, "memory"))
    sessions = SessionStore(os.path.join(wd, "miniclaude.db"))
    from miniclaude.cli.textual_app import MiniClaudeTUI
    tools = [tool_read, tool_write, tool_edit, create_tool_bash(wd),
             tool_grep, tool_glob, tool_web_fetch]
    agent = AgentLoop(model, tools, sessions.checkpointer, memory, config)
    app = MiniClaudeTUI(agent, config)
    app.set_working_dir(wd)
    app.run()


if __name__ == "__main__":
    if "--tui" in sys.argv:
        main_tui()
    else:
        asyncio.run(main())

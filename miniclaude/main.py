"""miniClaude 入口 —— 初始化组件、启动 REPL 循环。"""

import asyncio
import os
from datetime import datetime

from miniclaude.agent.agent_loop import AgentLoop
from miniclaude.agent.context_manager import ContextManager
from miniclaude.agent.subagent import SubagentRunner
from miniclaude.cli.rich_console import RichConsole
from miniclaude.config.app_config import Config
from miniclaude.llm.model_factory import create_model
from miniclaude.mcp.client import MCPClient
from miniclaude.mcp.tool_adapter import adapt_mcp_tools
from miniclaude.memory.memory_manager import MemoryManager
from miniclaude.memory.memory_tools import (
    set_memory_manager,
    tool_memory_forget,
    tool_memory_recall,
    tool_memory_save,
)
from miniclaude.storage.sqlite_store import SqliteStore
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

HELP_TEXT = """[bold]可用命令:[/]
  /exit       退出程序
  /help       显示此帮助
  /clear      清屏
  /model      显示当前模型信息
  /allow PAT  添加允许规则 (如 /allow bash:echo*)
  /compact    压缩对话上下文（总结历史）"""


async def main() -> None:
    """miniClaude 主入口。"""
    # 1. 加载配置
    config = Config.load()
    if not config.llm_api_key:
        print("错误: 未设置 DEEPSEEK_API_KEY，请在 .env 文件中配置")
        return

    # 2. 初始化控制台
    console = RichConsole()
    console.print_welcome()

    # 3. 初始化模型
    try:
        model = create_model(config)
    except Exception as e:
        console.print_error(f"无法初始化模型: {e}")
        return

    # 3.5. 初始化 MCP（连接外部工具服务器）
    mcp_client = MCPClient("mcp.json", console._console)
    mcp_client.parse_servers()
    if mcp_client._servers:
        console.print_system("[dim]正在连接 MCP Servers...[/dim]")
        await mcp_client.connect_all()
        mcp_tools = adapt_mcp_tools(mcp_client.get_all_tools())
        console.print_system(f"[dim]MCP: {len(mcp_tools)} 个外部工具[/dim]")
    else:
        mcp_tools = []

    # 4. 初始化 SQLite 持久化
    db_path = os.path.join(os.getcwd(), "miniclaude.db")
    db = SqliteStore(db_path)
    stats = db.get_stats()
    console.print_system(f"[dim]SQLite: {stats['conversations']} 条对话, {stats['memories']} 条记忆[/dim]")

    # 5. 初始化上下文管理器
    ctx_manager = ContextManager(max_turns=config.max_turns)

    # 6. 初始化记忆系统（双写：文件 + SQLite）
    memory_dir = os.path.join(os.getcwd(), "memory")
    memory_manager = MemoryManager(memory_dir, db)
    set_memory_manager(memory_manager)

    # 7. 初始化权限管理器
    perm_manager = PermissionManager()

    # 8. 初始化基础工具
    working_dir = os.getcwd()
    raw_tools = [
        tool_read,
        tool_write,
        tool_edit,
        create_tool_bash(working_dir),
        tool_grep,
        tool_glob,
        tool_web_fetch,
        tool_todo_write,
        tool_memory_save,
        tool_memory_recall,
        tool_memory_forget,
    ]
    # 9. 初始化子代理系统
    subagent_runner = SubagentRunner(model, raw_tools)
    task_tool = setup_task_tool(subagent_runner, working_dir)
    raw_tools.append(task_tool)

    # 9.5. 添加 MCP 工具（不经过权限守卫，MCP Server 自行管理权限）
    raw_tools.extend(mcp_tools)
    tools = [
        wrap_tool_with_permission(t, perm_manager, _ask_permission(console))
        for t in raw_tools
    ]

    # 11. 初始化 Agent
    agent = AgentLoop(model, tools, config, memory_manager)

    # 12. REPL 循环
    session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    while True:
        try:
            user_input = _read_input()

            if not user_input.strip():
                continue

            if user_input.startswith("/"):
                _handle_command(user_input, console, perm_manager, ctx_manager)
                continue

            console.print_user(user_input)
            console.show_thinking()

            # 注入上下文摘要
            context_injection = ctx_manager.get_injection()
            final_text = await agent.run_stream(
                user_input,
                working_dir=working_dir,
                context_injection=context_injection,
                on_text=_on_text(console),
                on_tool_start=_on_tool_start(console),
                on_tool_end=_on_tool_end(console),
            )

            console.hide_thinking()
            console.finish_assistant()

            # 记录本轮对话（SQLite + ContextManager）
            if final_text:
                turn_idx = db.get_turn_count(session_id)
                db.save_turn(session_id, "user", user_input, turn_index=turn_idx)
                db.save_turn(session_id, "assistant", final_text, turn_index=turn_idx)
                ctx_manager.add_turn(user_input, final_text)

            # 检查是否需要提示压缩
            if ctx_manager.should_compact():
                console.print_system(
                    f"[dim]对话已 {ctx_manager.turn_count} 轮，建议 /compact 压缩上下文[/dim]"
                )

            if final_text and console._renderer.buffer == "":
                console._console.print(final_text)

        except KeyboardInterrupt:
            console.hide_thinking()
            console.finish_assistant()
            console.print_system("[dim]已中断，输入新消息或 /exit 退出[/dim]")
            continue

        except EOFError:
            console.print_system("再见！")
            break

        except Exception as e:
            console.hide_thinking()
            console.print_error(f"运行出错: {e}")
            continue


def _ask_permission(console: RichConsole):
    """返回 on_ask 回调 —— 通过 CLI 询问用户是否允许工具执行。"""
    def handler(tool_name: str, key: str, args: dict, reason: str) -> bool | None:
        console.hide_thinking()
        console._console.print()
        console._console.print(
            f"  [bold yellow]🔒 权限确认[/] — {reason}"
        )
        console._console.print(f"  [dim]工具: {tool_name}[/dim]")
        if key:
            console._console.print(f"  [dim]目标: {key}[/dim]")

        from rich.prompt import Prompt
        choice = Prompt.ask(
            "  [y=允许一次 / a=允许本次会话 / n=拒绝]",
            choices=["y", "a", "n"],
            default="n",
        )
        console._console.print()
        # 权限确认后不重新显示 spinner，避免残留

        if choice == "a":
            return True   # 允许并记住
        elif choice == "y":
            return None   # 仅本次允许
        return False      # 拒绝

    return handler


def _on_text(console: RichConsole):
    """返回 on_text 回调 —— 隐藏 spinner 并渲染文本。"""
    def handler(text: str) -> None:
        console.hide_thinking()
        console.render_stream(text)

    return handler


def _on_tool_start(console: RichConsole):
    """返回 on_tool_start 回调（闭包捕获 console）。"""
    def handler(name: str, args: dict) -> None:
        console.hide_thinking()
        console.show_tool_call(name, args)
    return handler


def _on_tool_end(console: RichConsole):
    """返回 on_tool_end 回调（闭包捕获 console）。"""
    def handler(name: str, output: str) -> None:
        console.show_tool_result(name, output)
    return handler


def _read_input() -> str:
    """读取用户输入。"""
    from rich.prompt import Prompt
    return Prompt.ask("")


def _handle_command(
    cmd: str, console: RichConsole, perm_manager: PermissionManager,
    ctx_manager: ContextManager,
) -> None:
    """处理 / 开头的命令。"""
    cmd = cmd.strip().lower()

    if cmd == "/exit":
        console.print_system("再见！")
        raise EOFError()
    elif cmd == "/help":
        console._console.print(HELP_TEXT)
    elif cmd == "/clear":
        os.system("cls" if os.name == "nt" else "clear")
    elif cmd == "/model":
        config = Config.load()
        console.print_system(
            f"模型: {config.llm_model}\n"
            f"API: {config.llm_base_url}\n"
            f"最大轮次: {config.max_turns}"
        )
    elif cmd.startswith("/allow"):
        parts = cmd.split(None, 1)
        if len(parts) == 2:
            pattern = parts[1]
            perm_manager.add_rule(pattern, "allow")
            console.print_system(f"规则已添加: {pattern} → allow")
        else:
            console.print_system("用法: /allow <pattern>  如 /allow bash:echo*")
    elif cmd == "/compact":
        t = ctx_manager.turn_count
        if t == 0:
            console.print_system("没有需要压缩的对话历史")
        else:
            prompt = ctx_manager.build_compact_prompt()
            ctx_manager.compact(
                f"以下是从 {t} 轮对话中总结的关键信息: {prompt[:300]}"
            )
            console.print_system(f"已压缩 {t} 轮对话，摘要将注入后续上下文")
    else:
        console.print_system(f"未知命令: {cmd}，输入 /help 查看帮助")


if __name__ == "__main__":
    asyncio.run(main())

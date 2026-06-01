"""miniClaude 入口 —— 初始化组件、启动 REPL 循环。"""

import asyncio
import os

from miniclaude.agent.agent_loop import AgentLoop
from miniclaude.cli.rich_console import RichConsole
from miniclaude.config.app_config import Config
from miniclaude.llm.model_factory import create_model
from miniclaude.tools.permission import PermissionManager, wrap_tool_with_permission
from miniclaude.tools.tool_bash import create_tool_bash
from miniclaude.tools.tool_edit import tool_edit
from miniclaude.tools.tool_glob import tool_glob
from miniclaude.tools.tool_grep import tool_grep
from miniclaude.tools.tool_read import tool_read
from miniclaude.tools.tool_write import tool_write

HELP_TEXT = """[bold]可用命令:[/]
  /exit       退出程序
  /help       显示此帮助
  /clear      清屏
  /model      显示当前模型信息
  /allow PAT  添加允许规则 (如 /allow bash:echo*)"""


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

    # 4. 初始化权限管理器
    perm_manager = PermissionManager()

    # 5. 初始化工具并包装权限守卫
    working_dir = os.getcwd()
    raw_tools = [
        tool_read,
        tool_write,
        tool_edit,
        create_tool_bash(working_dir),
        tool_grep,
        tool_glob,
    ]
    tools = [
        wrap_tool_with_permission(t, perm_manager, _ask_permission(console))
        for t in raw_tools
    ]

    # 6. 初始化 Agent
    agent = AgentLoop(model, tools, config)

    # 7. REPL 循环
    while True:
        try:
            user_input = _read_input()

            if not user_input.strip():
                continue

            if user_input.startswith("/"):
                _handle_command(user_input, console, perm_manager)
                continue

            console.print_user(user_input)
            console.show_thinking()

            final_text = await agent.run_stream(
                user_input,
                working_dir=working_dir,
                on_text=_on_text(console),
                on_tool_start=_on_tool_start(console),
                on_tool_end=_on_tool_end(console),
            )

            console.hide_thinking()
            console.finish_assistant()

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
        console.show_thinking()

        if choice == "a":
            return True   # 允许并记住
        elif choice == "y":
            return None   # 仅本次允许
        return False      # 拒绝

    return handler


def _on_text(console: RichConsole):
    """返回 on_text 回调 —— 首次收到文本时隐藏 spinner。"""
    first_text = True

    def handler(text: str) -> None:
        nonlocal first_text
        if first_text:
            console.hide_thinking()
            first_text = False
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
        console.show_thinking()
    return handler


def _read_input() -> str:
    """读取用户输入。"""
    from rich.prompt import Prompt
    return Prompt.ask("")


def _handle_command(cmd: str, console: RichConsole, perm_manager: PermissionManager) -> None:
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
    else:
        console.print_system(f"未知命令: {cmd}，输入 /help 查看帮助")


if __name__ == "__main__":
    asyncio.run(main())

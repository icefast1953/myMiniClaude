"""miniClaude 入口 —— 初始化组件、启动 REPL 循环。"""

import asyncio
import os

from miniclaude.agent.agent_loop import AgentLoop
from miniclaude.cli.rich_console import RichConsole
from miniclaude.config.app_config import Config
from miniclaude.llm.model_factory import create_model
from miniclaude.tools.tool_bash import create_tool_bash
from miniclaude.tools.tool_edit import tool_edit
from miniclaude.tools.tool_glob import tool_glob
from miniclaude.tools.tool_grep import tool_grep
from miniclaude.tools.tool_read import tool_read
from miniclaude.tools.tool_write import tool_write

HELP_TEXT = """[bold]可用命令:[/]
  /exit    退出程序
  /help    显示此帮助
  /clear   清屏
  /model   显示当前模型信息"""


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

    # 4. 初始化工具
    working_dir = os.getcwd()
    tools = [
        tool_read,
        tool_write,
        tool_edit,
        create_tool_bash(working_dir),
        tool_grep,
        tool_glob,
    ]

    # 5. 初始化 Agent
    agent = AgentLoop(model, tools, config)

    # 6. REPL 循环
    while True:
        try:
            user_input = _read_input()

            if not user_input.strip():
                continue

            if user_input.startswith("/"):
                _handle_command(user_input, console)
                continue

            console.print_user(user_input)
            console.show_thinking()

            final_text = await agent.run_stream(
                user_input,
                working_dir=working_dir,
                on_text=lambda text: console.render_stream(text),
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


def _handle_command(cmd: str, console: RichConsole) -> None:
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
    else:
        console.print_system(f"未知命令: {cmd}，输入 /help 查看帮助")


if __name__ == "__main__":
    asyncio.run(main())

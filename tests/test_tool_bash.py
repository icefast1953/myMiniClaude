"""测试 Bash 工具。"""

import pytest
from miniclaude.tools.tool_bash import create_tool_bash


@pytest.fixture
def bash():
    return create_tool_bash(".")


@pytest.mark.asyncio
async def test_bash_echo(bash):
    result = await bash.ainvoke({"command": "echo hello", "description": "test"})
    assert "hello" in result


@pytest.mark.asyncio
async def test_bash_failed_command(bash):
    result = await bash.ainvoke({"command": "exit 1", "description": "test"})
    assert "错误" in result or "[退出码: 1]" in result


@pytest.mark.asyncio
async def test_bash_nonexistent_command(bash):
    result = await bash.ainvoke({
        "command": "cmd_does_not_exist_xyz", "description": "test",
    })
    assert "错误" in result or "未找到" in result

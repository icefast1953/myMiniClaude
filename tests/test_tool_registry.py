"""测试 ToolRegistry。"""

from miniclaude.tools.tool_registry import ToolRegistry
from miniclaude.tools.tool_read import tool_read
from miniclaude.tools.tool_glob import tool_glob


def test_register_and_get():
    reg = ToolRegistry()
    reg.register(tool_read)
    assert reg.get("read") is tool_read
    assert reg.get("nonexistent") is None


def test_list_names():
    reg = ToolRegistry()
    reg.register(tool_read)
    reg.register(tool_glob)
    assert set(reg.list_names()) == {"read", "glob"}


def test_get_langchain_tools():
    reg = ToolRegistry()
    reg.register(tool_read)
    tools = reg.get_langchain_tools()
    assert len(tools) == 1
    assert tools[0] is tool_read


def test_override():
    reg = ToolRegistry()
    reg.register(tool_read)
    reg.register(tool_read)
    assert len(reg.get_all()) == 1

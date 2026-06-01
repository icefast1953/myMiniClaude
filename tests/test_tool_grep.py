"""测试 Grep 工具。"""

import pytest
from miniclaude.tools.tool_grep import tool_grep


@pytest.mark.asyncio
async def test_grep_basic(temp_dir):
    (temp_dir / "a.py").write_text("def hello():\n    pass\n")
    result = await tool_grep.ainvoke({"pattern": "hello", "path": str(temp_dir)})
    assert "hello" in result
    assert "a.py" in result


@pytest.mark.asyncio
async def test_grep_no_match(temp_dir):
    (temp_dir / "x.py").write_text("abc")
    result = await tool_grep.ainvoke({
        "pattern": "zzz_no_match_zzz", "path": str(temp_dir),
    })
    assert "未找到" in result


@pytest.mark.asyncio
async def test_grep_invalid_regex(temp_dir):
    result = await tool_grep.ainvoke({"pattern": "[invalid", "path": str(temp_dir)})
    assert result.startswith("错误:")


@pytest.mark.asyncio
async def test_grep_nonexistent_path():
    result = await tool_grep.ainvoke({
        "pattern": "test", "path": "/not/exist/path",
    })
    assert result.startswith("错误:")

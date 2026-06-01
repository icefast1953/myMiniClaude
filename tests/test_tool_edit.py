"""测试 Edit 工具。"""

import pytest
from miniclaude.tools.tool_edit import tool_edit


@pytest.mark.asyncio
async def test_edit_exact_match(temp_dir):
    path = temp_dir / "e.txt"
    path.write_text("hello world")
    result = await tool_edit.ainvoke({
        "file_path": str(path), "old_text": "hello", "new_text": "hi",
    })
    assert "已编辑" in result
    assert path.read_text() == "hi world"


@pytest.mark.asyncio
async def test_edit_no_match(temp_dir):
    path = temp_dir / "e.txt"
    path.write_text("hello")
    result = await tool_edit.ainvoke({
        "file_path": str(path), "old_text": "xyz", "new_text": "abc",
    })
    assert "未找到匹配" in result or result.startswith("错误:")


@pytest.mark.asyncio
async def test_edit_multiple_matches(temp_dir):
    path = temp_dir / "e.txt"
    path.write_text("hello and hello")
    result = await tool_edit.ainvoke({
        "file_path": str(path), "old_text": "hello", "new_text": "hi",
    })
    assert "2 处匹配" in result or result.startswith("错误:")


@pytest.mark.asyncio
async def test_edit_nonexistent_file(temp_dir):
    result = await tool_edit.ainvoke({
        "file_path": str(temp_dir / "x.txt"), "old_text": "a", "new_text": "b",
    })
    assert result.startswith("错误:")

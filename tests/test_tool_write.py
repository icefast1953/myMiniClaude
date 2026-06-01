"""测试 Write 工具。"""

import pytest
from miniclaude.tools.tool_write import tool_write


@pytest.mark.asyncio
async def test_write_new_file(temp_dir):
    path = temp_dir / "out.txt"
    result = await tool_write.ainvoke({"file_path": str(path), "content": "hi"})
    assert "已写入" in result
    assert path.read_text() == "hi"


@pytest.mark.asyncio
async def test_write_creates_parent_dirs(temp_dir):
    path = temp_dir / "a" / "b" / "f.txt"
    await tool_write.ainvoke({"file_path": str(path), "content": "x"})
    assert path.read_text() == "x"


@pytest.mark.asyncio
async def test_write_overwrite(temp_dir):
    path = temp_dir / "f.txt"
    path.write_text("old")
    await tool_write.ainvoke({"file_path": str(path), "content": "new"})
    assert path.read_text() == "new"


@pytest.mark.asyncio
async def test_write_directory_fails(temp_dir):
    result = await tool_write.ainvoke({"file_path": str(temp_dir), "content": "x"})
    assert result.startswith("错误:")

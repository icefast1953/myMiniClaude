"""测试 Read 工具。"""

import pytest
from miniclaude.tools.tool_read import tool_read


@pytest.mark.asyncio
async def test_read_existing_file(sample_file):
    path, _ = sample_file
    result = await tool_read.ainvoke({"file_path": str(path)})
    assert "line 1:" in result
    assert "line 2:" in result


@pytest.mark.asyncio
async def test_read_nonexistent_file(temp_dir):
    result = await tool_read.ainvoke({"file_path": str(temp_dir / "nope.txt")})
    assert result.startswith("错误:")


@pytest.mark.asyncio
async def test_read_with_offset_limit(sample_file):
    path, _ = sample_file
    result = await tool_read.ainvoke({
        "file_path": str(path), "offset": 2, "limit": 1,
    })
    assert result.startswith("2\t")


@pytest.mark.asyncio
async def test_read_directory(temp_dir):
    result = await tool_read.ainvoke({"file_path": str(temp_dir)})
    assert result.startswith("错误:")

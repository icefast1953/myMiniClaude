"""测试 Glob 工具。"""

import pytest
from miniclaude.tools.tool_glob import tool_glob


@pytest.mark.asyncio
async def test_glob_py_files(temp_dir):
    (temp_dir / "a.py").touch()
    (temp_dir / "b.py").touch()
    (temp_dir / "c.txt").touch()
    result = await tool_glob.ainvoke({"pattern": "*.py", "path": str(temp_dir)})
    assert "a.py" in result
    assert "b.py" in result
    assert "c.txt" not in result


@pytest.mark.asyncio
async def test_glob_recursive(temp_dir):
    sub = temp_dir / "sub"
    sub.mkdir()
    (sub / "d.py").touch()
    result = await tool_glob.ainvoke({"pattern": "**/*.py", "path": str(temp_dir)})
    assert "d.py" in result


@pytest.mark.asyncio
async def test_glob_no_match(temp_dir):
    result = await tool_glob.ainvoke({"pattern": "*.xyz", "path": str(temp_dir)})
    assert "未找到" in result


@pytest.mark.asyncio
async def test_glob_nonexistent_path():
    result = await tool_glob.ainvoke({"pattern": "*", "path": "/not/exist"})
    assert result.startswith("错误:")

"""pytest fixtures —— 为测试提供临时工作目录、配置和 Mock 对象。"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from miniclaude.config.app_config import Config


@pytest.fixture
def temp_dir():
    """临时工作目录，测试结束后自动清理。"""
    with tempfile.TemporaryDirectory() as tmp:
        orig = os.getcwd()
        os.chdir(tmp)
        yield Path(tmp)
        os.chdir(orig)


@pytest.fixture
def test_config():
    """提供测试用 Config，不依赖 .env 文件。"""
    return Config(
        llm_api_key="test-key",
        llm_base_url="https://test.api.com",
        llm_model="test-model",
        max_turns=10,
        max_retries=1,
        tool_timeout=60,
    )


@pytest.fixture
def sample_file(temp_dir):
    """创建一个包含已知内容的测试文件。"""
    path = temp_dir / "sample.txt"
    content = "line 1: hello\nline 2: world\nline 3: hello again\n"
    path.write_text(content)
    return path, content


@pytest.fixture
def mock_model():
    """Mock ChatOpenAI，用于 Agent 集成测试。"""
    model = MagicMock()
    model.model_name = "test-model"
    return model

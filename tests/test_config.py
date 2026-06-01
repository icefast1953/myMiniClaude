"""测试 Config 配置加载。"""

from miniclaude.config.app_config import Config


def test_config_defaults():
    config = Config()
    assert config.llm_model == "deepseek-chat"
    assert config.max_turns == 50
    assert config.max_retries == 3


def test_config_custom():
    config = Config(llm_api_key="k", llm_model="m", max_turns=99)
    assert config.llm_api_key == "k"
    assert config.llm_model == "m"
    assert config.max_turns == 99
    assert config.max_retries == 3  # 默认值不变


def test_config_immutable():
    config = Config()
    try:
        config.max_turns = 100  # type: ignore
        assert False, "frozen 应抛出异常"
    except Exception:
        pass


def test_config_singleton():
    c1 = Config.load()
    c2 = Config.load()
    assert c1 is c2

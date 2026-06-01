"""模型工厂 —— 根据配置创建 LangChain ChatModel 实例。

首期支持 DeepSeek（OpenAI 兼容），后续扩展 Anthropic、OpenAI 等后端。
"""

from langchain_openai import ChatOpenAI

from miniclaude.config.app_config import Config


def create_model(config: Config | None = None) -> ChatOpenAI:
    """根据配置创建 DeepSeek（OpenAI 兼容）ChatModel。

    所有配置来自 Config，包括 api_key、base_url、model 名称。
    """
    if config is None:
        config = Config.load()

    return ChatOpenAI(
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
        model=config.llm_model,
        temperature=0.7,
        max_tokens=4096,
        streaming=True,
    )

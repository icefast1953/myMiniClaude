"""配置管理模块 —— 加载 .env 文件，提供类型安全的配置访问。"""

import os
from dataclasses import dataclass
from typing import ClassVar

from dotenv import load_dotenv

# 模块加载时自动寻找并加载 .env 文件
load_dotenv()


@dataclass(frozen=True)
class Config:
    """miniClaude 全局配置。frozen=True 确保实例化后不可变。

    优先级：.env 文件 > 环境变量 > 默认值。
    """

    # LLM 配置
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"

    # Agent 配置
    max_turns: int = 50
    max_retries: int = 3
    tool_timeout: int = 120

    # 单例实例
    _instance: ClassVar["Config | None"] = None

    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量构建 Config。"""
        return cls(
            llm_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            llm_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            llm_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            max_turns=int(os.getenv("MAX_TURNS", "50")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            tool_timeout=int(os.getenv("TOOL_TIMEOUT", "120")),
        )

    @classmethod
    def load(cls) -> "Config":
        """获取全局配置单例，首次调用时从环境变量加载。"""
        if cls._instance is None:
            cls._instance = cls.from_env()
        return cls._instance


# 模块级便捷单例
config = Config.load()

# 开发指南

## 环境搭建

```bash
git clone https://github.com/icefast1953/myMiniClaude.git
cd miniClaude
uv sync
cp .env.example .env  # 编辑填入 DEEPSEEK_API_KEY
```

## 运行

```bash
uv run python -m miniclaude.main
```

## 测试

```bash
uv run --active pytest tests/ -v
uv run --active pytest tests/ --cov=miniclaude -v
```

## 项目结构

```
miniClaude/
├── miniclaude/           # 主包
│   ├── main.py           # 入口
│   ├── agent/            # Agent 层 (system_prompt + agent_loop)
│   ├── llm/              # LLM 层 (model_factory + message_types)
│   ├── tools/            # 工具集 (6 个工具 + registry)
│   ├── cli/              # CLI (RichConsole + MarkdownRenderer)
│   └── config/           # 配置 (app_config)
├── docs/                 # 文档
├── tests/                # 31 个测试
└── pyproject.toml        # 项目配置
```

## 技术栈

| 组件 | 库 |
|------|-----|
| Agent 框架 | langgraph |
| LLM 接口 | langchain-openai (ChatOpenAI) |
| CLI 渲染 | rich |
| 配置 | python-dotenv |
| 测试 | pytest + pytest-asyncio |
| 包管理 | uv |

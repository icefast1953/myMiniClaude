# miniClaude 架构文档

## 模块依赖图

```
main.py (入口)
  ├── config/app_config.py     # 配置管理
  ├── cli/rich_console.py      # CLI 视觉
  │     └── markdown_render.py # 流式 Markdown 渲染
  ├── llm/model_factory.py     # 模型工厂
  │     └── langchain_openai.ChatOpenAI
  ├── tools/                   # 工具集
  │     ├── tool_read.py       ──┐
  │     ├── tool_write.py      ──┤
  │     ├── tool_edit.py       ──┤
  │     ├── tool_bash.py       ──┼── @tool 装饰器
  │     ├── tool_grep.py       ──┤
  │     ├── tool_glob.py       ──┤
  │     └── tool_registry.py   ──┘
  └── agent/
        ├── system_prompt.py   # 中文 System Prompt
        └── agent_loop.py      # langgraph ReAct Agent
```

## 数据流

```
用户输入 "读取 README.md"
  → AgentLoop.run_stream()
    → SystemMessage + HumanMessage → langgraph
      → LLM 返回 tool_call { name: "read", args: {...} }
        → langgraph 自动执行 tool_read
          → 结果追加到对话上下文 → LLM 生成文本回复
            → on_text 回调 → MarkdownRenderer → 终端流式输出
```

## 关键设计决策 (ADR)

1. **langgraph vs 手写循环**: 选 langgraph，减少状态管理代码
2. **@tool 装饰器 vs 自定义基类**: 选 @tool，代码量减少 32%
3. **ChatOpenAI vs openai SDK**: 选 ChatOpenAI，langchain 生态兼容
4. **回调 vs 直接依赖**: Agent 层通过回调与 CLI 解耦，便于测试
5. **中文 System Prompt**: 面向中文用户，动态信息通过 user message 注入

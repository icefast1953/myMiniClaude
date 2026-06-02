# miniClaude 架构文档

> 最后更新: 2026-06-02 | 模型: deepseek-v4-flash (1M context)

## 模块依赖图

```
main.py (入口, async)
  ├── config/app_config.py       # 配置管理 (.env + frozen dataclass)
  ├── cli/                       # 用户界面
  │     └── rich_console.py      # Rich REPL (流式 Markdown)
  ├── llm/model_factory.py       # 模型工厂 (ChatOpenAI, deepseek-v4-flash)
  │
  ├── agent/
  │     ├── system_prompt.py     # 中文 System Prompt + 动态上下文 (Windows 适配)
  │     ├── agent_loop.py        # create_agent + AsyncSqliteSaver checkpoint
  │     ├── token_budgeter.py    # Token 预算 + 三级降级压缩 (async state)
  │     ├── task_classifier.py   # 四层任务分类 (L1显式/L2意图/L3上下文/L4阶段)
  │     ├── compressor.py        # L1 规则压缩 + L2+L3 LLM 双输出
  │     └── subagent.py          # 子代理 (探索/研究/编码)
  │
  ├── tools/                     # 工具集 (12 + MCP)
  │     ├── permission.py        # 权限 (READ/WRITE/DANGER, 工具级白名单)
  │     └── tool_read / write / edit / bash / grep / glob / ...
  │
  ├── memory/                    # 长期记忆 (文件+SQLite 双写)
  ├── mcp/                       # MCP 协议
  └── storage/                   # 持久化
        └── session_store.py     # AsyncSqliteSaver + 会话复用 + 空会话清理
  │     └── tool_adapter.py      # JSON Schema → Pydantic
  │
  └── storage/
        └── session_store.py     # 会话 CRUD + SqliteSaver
```

## 记忆系统双层架构

```
长期记忆（跨会话）              短期记忆（当前会话）
  memory/MEMORY.md 索引          SqliteSaver checkpoint
  memory/*.md 具体记忆           sessions 表（元数据）
  自动聚合 (>20条触发)           TokenBudgeter 监控
  memory_save / recall / forget  /sessions /new /switch
```

## 数据流

```
用户输入 → TokenBudgeter.check() → AgentLoop.run_stream()
  → 长期记忆注入 (MemoryManager)
  → SystemMessage + HumanMessage
  → langgraph (SqliteSaver checkpoint)
  → LLM → tool_call → 工具执行 → 回写 checkpoint
  → LLM 续写 → 流式输出
```

## 关键设计决策 (ADR)

1. langgraph over 手写循环 — 减少状态管理
2. SqliteSaver over 手动消息管理 — 自动持久化
3. @tool 装饰器 over 自定义基类 — 代码量-32%
4. ChatOpenAI over openai SDK — langchain 兼容
5. 回调解耦 Agent 与 CLI — 便于测试
6. 文件+SQLite 双写 — 可靠性优先
7. 中文 System Prompt — 动态信息通过 user message 注入

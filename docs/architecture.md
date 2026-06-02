# miniClaude 架构文档

## 模块依赖图

```
main.py (入口)
  ├── config/app_config.py       # 配置管理 (.env + 默认值)
  ├── cli/                       # 用户界面
  │     ├── rich_console.py      # Rich REPL
  │     └── textual_app.py       # Textual TUI (--tui)
  ├── llm/model_factory.py       # 模型工厂 (ChatOpenAI)
  │
  ├── agent/
  │     ├── system_prompt.py     # 中文 System Prompt
  │     ├── agent_loop.py        # langgraph ReAct + SqliteSaver
  │     ├── token_budgeter.py    # Token 预算监控
  │     └── subagent.py          # 子代理系统
  │
  ├── tools/                     # 工具集 (12 + MCP)
  │     ├── tool_read / write / edit / bash / grep / glob
  │     ├── tool_task.py         # 子代理任务
  │     ├── permission.py        # 权限控制系统
  │     └── tool_web_fetch / tool_todo_write
  │
  ├── memory/                    # 长期记忆
  │     ├── memory_manager.py    # 索引 + 全文 + 自动聚合
  │     └── memory_tools.py      # save / recall / forget
  │
  ├── mcp/                       # MCP 协议
  │     ├── client.py            # stdio 连接管理
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

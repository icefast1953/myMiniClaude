# miniClaude

仿造 Claude Code 的轻量级 AI 编程助手。

## 核心能力

### Agent 引擎
- **langgraph ReAct Agent** — 自动 tool use 循环
- **SqliteSaver checkpoint** — 对话状态持久化，重启恢复
- **流式 Markdown 输出** — 逐 token 渲染

### 工具系统 (12 内置 + MCP)
- 文件: Read / Write / Edit
- 搜索: Grep / Glob / WebFetch
- 执行: Bash
- 记忆: memory_save / recall / forget
- 组织: TodoWrite / Task (子代理)
- **MCP 协议** — stdio 连接外部工具服务器

### 权限控制
- 3 级: y (一次) / a (记住) / n (拒绝)
- 规则白名单: `/allow bash:echo*`

### 记忆系统 (双层)

| | 短期记忆 | 长期记忆 |
|------|------|------|
| 存储 | SqliteSaver checkpoint | memory/*.md + MEMORY.md 索引 |
| 生命周期 | 当前会话 | 跨会话永久 |
| 写入 | 自动持久化 | LLM 显式调用 |
| 管理 | /sessions /new /switch | /memory /compact |
| 辅助 | TokenBudgeter (4k/8k) | 自动聚合 (>20条) |

### 会话管理
- `/sessions` 列表, `/new` 新建, `/switch` 切换
- 每会话独立 checkpoint，自动恢复历史

### 双界面
```bash
uv run python -m miniclaude.main          # Rich REPL
uv run python -m miniclaude.main --tui    # Textual TUI
```

## 文档

- [架构文档](docs/architecture.md)
- [记忆系统](docs/memory-design.md)
- [工具系统](docs/tools.md)
- [LLM 后端](docs/llm_backend.md)
- [开发指南](docs/development.md)

## 快速开始

```bash
uv sync
echo "DEEPSEEK_API_KEY=sk-xxx" > .env
uv run python -m miniclaude.main
```

## 设计决策

| 决策 | 选择 |
|------|------|
| Agent 框架 | langgraph ReAct |
| 对话持久化 | SqliteSaver checkpoint |
| 工具定义 | @tool 装饰器 |
| 记忆存储 | 文件 + SQLite 双写 |
| LLM 适配 | ChatOpenAI 兼容 |
| Token 估算 | 字符数 / 3.5 |

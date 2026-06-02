# 记忆系统设计

## 双层架构

```
┌──────────────────────────────────────────────┐
│              miniClaude 记忆系统              │
├────────────────────┬─────────────────────────┤
│   短期记忆 (会话内)  │   长期记忆 (跨会话)       │
│                    │                         │
│ SqliteSaver        │ MemoryManager           │
│   checkpoint       │   memory/MEMORY.md 索引  │
│ sessions 表        │   memory/*.md 正文       │
│ TokenBudgeter      │   自动聚合                │
│                    │                         │
│ 自动持久化          │ LLM 显式调用             │
│ /sessions /new     │ memory_save/recall/forget│
│ /switch /compact   │ /memory 查看             │
└────────────────────┴─────────────────────────┘
```

## 短期记忆

### SqliteSaver Checkpoint

langgraph 的 SqliteSaver 在每次 `agent.ainvoke()` 后自动保存完整状态：

```python
from langgraph.checkpoint.sqlite import SqliteSaver
checkpointer = SqliteSaver.from_conn_string("miniclaude.db")
agent = create_react_agent(model, tools, checkpointer=checkpointer)
# 同一 thread_id 自动恢复历史
config = {"configurable": {"thread_id": session_id}}
await agent.ainvoke({"messages": [HumanMessage(...)]}, config=config)
```

### SessionStore 会话管理

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | `20260602-143025-a1b2c3` |
| title | TEXT | 会话标题 |
| turn_count | INT | 对话轮数 |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

命令: `/sessions` `/new` `/switch <id>`

### TokenBudgeter

| 阈值 | 默认值 | 动作 |
|------|------|------|
| WARNING | 4000 | 终端显示用量提示 |
| COMPACT | 8000 | 自动压缩 |
| KEEP_RECENT | 5 轮 | 压缩后保留 |

### compact 执行流程

```
每轮对话前 → TokenBudgeter.check()
  → should_compact=True
    → 分离旧消息 (保留最近 KEEP_RECENT*2 条)
    → 取旧消息最近 30 条 → LLM 生成 200 字摘要
    → agent.update_state() 替换为 [summary_msg] + recent_msgs
    → 日志: "压缩完成: 48 条 → 1 条摘要 (节省 ~3500 tokens)"
  → should_warn → 仅显示用量提示
```

## 长期记忆

### 文件结构

```
memory/
├── MEMORY.md    ← 索引 (一行一条，快速扫描)
├── user-prefs.md → 具体记忆
└── ...
```

### 记忆格式 (YAML frontmatter + Markdown)

```markdown
---
name: user-prefs
description: 用户偏好
metadata: {type: user}
---
用户使用中文交流，偏好简洁。
```

### 自动聚合

索引 > 20 条 → `should_aggregate()` → `build_aggregation_prompt()` → LLM 整理

### 上下文注入

每轮对话注入索引摘要:
```
[长期记忆] 共 3 条:
- [user-prefs](user-prefs.md) — 语言偏好
```

## 3 个工具

| 工具 | 动作 |
|------|------|
| `memory_save` | 写文件 + 重建索引 |
| `memory_recall` | 关键字模糊搜索 |
| `memory_forget` | 删除 + 更新索引 |

## 启动流程

```
main.py
  → MemoryManager('memory/')  加载长期记忆
  → SessionStore('miniclaude.db')  初始化 SqliteSaver
  → TokenBudgeter()  预算监控
  → AgentLoop(model, tools, checkpointer, memory)
```

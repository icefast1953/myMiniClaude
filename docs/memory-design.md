# 记忆系统设计

> 更新: 2026-06-02 | AsyncSqliteSaver + 自适应 Token 压缩

## 三层架构

```
┌──────────────────────────────────────────────────────────┐
│                   miniClaude 记忆系统                     │
├──────────────────┬──────────────────┬────────────────────┤
│ 短期记忆 (会话内)  │ Token 预算 (压缩)  │ 长期记忆 (跨会话)    │
│                  │                  │                    │
│ AsyncSqliteSaver │ TokenBudgeter    │ MemoryManager      │
│   checkpoint     │   L1 规则 <1ms   │   memory/*.md      │
│ sessions 表      │   L2 LLM 摘要    │   MEMORY.md 索引    │
│                  │   L3 状态声明    │   自动聚合           │
│                  │                  │                    │
│                  │ TaskClassifier   │                    │
│                  │   四层分类        │                    │
│                  │   自适应阈值      │                    │
│                  │   (16K~64K)      │                    │
│                  │                  │                    │
│ 自动持久化        │ 超限自动触发      │ LLM 显式调用        │
│ /sessions /new   │ /compact /token  │ memory_save/recall │
│ /switch          │ /mode            │ /memory            │
└──────────────────┴──────────────────┴────────────────────┘
```

## 短期记忆

### AsyncSqliteSaver Checkpoint

```python
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
cm = AsyncSqliteSaver.from_conn_string("miniclaude.db")
checkpointer = await cm.__aenter__()
agent = create_agent(model, tools, checkpointer=checkpointer)
```

> 所有 state 访问必须用 async (`aget_state` / `aupdate_state`)。

### SessionStore

启动时**复用最近 0 轮会话**，`cleanup_empty()` 清理空会话。命令: `/sessions` `/new` `/switch`

## 自适应 Token 压缩

### 三级降级

```
TaskClassifier.profile() → 四层分类 → 自适应阈值
  ↓
TokenBudgeter.check() → aget_state() → 估算
  ↓ 超限
compact():
  L1 规则 (<1ms): ToolMessage → stats + head/tail → 估算 → OK? 停
  L2+L3 一次 LLM: L2 摘要 + L3 YAML → 选一个 → aupdate_state(REMOVE_ALL + new)
```

### 自适应阈值 (deepseek-v4-flash 1M context)

| 任务 | compact | keep | Level |
|------|---------|------|-------|
| code-gen | 16K | 3 轮 | L3 |
| explain/test | 24K | 5 轮 | L2 |
| refactor/default | 32K | 5-6 轮 | L2 |
| debug/env | 64K | 8-10 轮 | L1 |

## 长期记忆

文件 (`memory/*.md`) + SQLite 双写，LLM 通过 `memory_save/recall/forget` 工具管理。
索引 > 20 条自动聚合，每轮注入摘要。

## 启动流程

```
main.py
  → SessionStore → await async_init() → 复用会话
  → MemoryManager → 长期记忆
  → TaskClassifier + TokenBudgeter
  → AgentLoop(model, tools, checkpointer, memory)
```

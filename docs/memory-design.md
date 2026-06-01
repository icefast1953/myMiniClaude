# 记忆系统设计

## 概述

模仿 Claude Code 的 Memory 机制，跨会话持久化记忆。启动时自动加载并注入对话上下文。

## 存储：文件 + SQLite 双写

```
MemoryManager
  ├── 写入 → memory/{name}.md + miniclaude.db
  └── 读取 → 扫描文件 + 合并 SQLite（去重）
```

### 文件格式（`memory/xxx.md`）

```markdown
---
name: user-prefs
description: 用户偏好设置
metadata:
  type: user
---
用户使用中文交流，偏好简洁回复。
```

| 字段 | 作用 |
|------|------|
| `name` | 唯一标识（kebab-case），也作文件名 |
| `description` | 一行摘要，用于搜索匹配 |
| `content` | 记忆正文 |
| `type` | user / project / reference / feedback |

### SQLite 表

```sql
CREATE TABLE memories (
    name TEXT PRIMARY KEY,
    description TEXT,
    content TEXT,
    mem_type TEXT DEFAULT 'user',
    updated_at TEXT
);
```

## 3 个工具

| 工具 | 参数 | 动作 |
|------|------|------|
| `memory_save` | name, description, content, type | 写文件 + SQLite |
| `memory_recall` | query（关键词） | 模糊匹配 name/description/content |
| `memory_forget` | name | 删文件 + SQLite 记录 |

## 上下文注入

### 启动时

```
MemoryManager('memory/')._load_all()
  → 扫描 *.md → 反序列化 Memory 对象
  → 合并 SQLite 记录（去重）
  → 存入内存缓存
```

### 每轮对话

```
AgentLoop._build_context()
  → MemoryManager.get_context()
    → "[记忆] 以下是已保存的记忆:
        - [user-prefs] 用户偏好设置"
    → 注入到 UserMessage
```

### 完整消息示例

```
SystemMessage: "你是 miniClaude..."
UserMessage:
  "[系统信息] 今天 2026-06-01, 工作目录: /project
  
  [记忆] 已保存的记忆:
   - [user-prefs] 用户偏好设置
  
  用户: 帮我写函数"
```

## 与 ContextManager 的区别

| | ContextManager | MemoryManager |
|------|------|------|
| 范围 | 当前会话 | 跨会话 |
| 存储 | SQLite conversations 表 | 文件 + SQLite memories 表 |
| 生命周期 | 会话结束即归档 | 永久保留 |
| 管理方式 | /compact 压缩 | memory_save/recall/forget |

## 完整生命周期

```
1. 用户说 "记住我喜欢简洁回复"
2. LLM → memory_save("user-prefs", "回复风格", "用户喜欢简洁", "user")
3. 下次启动 → 自动注入 "[记忆] ...回复风格"
4. LLM 看到记忆 → 调整回复风格
5. 用户说 "忘掉那个偏好" → memory_forget("user-prefs")
```

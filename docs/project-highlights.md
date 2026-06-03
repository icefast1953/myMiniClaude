# miniClaude 项目亮点分析

> 本文档由求职助手（Job Hunt Copilot）生成，用于简历定制和模拟面试参考。
> 生成日期：2026-06-02 | 更新：2026-06-03（新增自适应压缩、自我纠错、Skill 系统）
>
> 📝 **面试准备请用**：[interview-prep.md](interview-prep.md) — 含口播稿、深挖问答库、简历文案

---

## 一句话定位

**用 ~1200 行 Python + langgraph 构建的轻量级 AI 编程助手，完整实现 Agent 引擎、三层记忆系统、工具调度与权限管控、MCP 协议集成。**

---

## STAR 总览

| STAR | 内容 |
|------|------|
| **S**ituation | AI 编程助手核心机制（Agent 循环、记忆系统、权限控制）是"黑盒"，企业急需能设计 Agent 系统的人才 |
| **T**ask | 从 0 构建完整 Agent 系统，亲手实现每一层架构，~1200 行约束，验证"合理选型→最少代码→最大能力" |
| **A**ction | 6 个关键决策：langgraph 基座选型、三层记忆拆解、工具包装式权限、MCP 动态 Schema 适配、子 Agent 编排、防御性工具设计 |
| **R**esult | 8 模块解耦、12 工具+MCP、三层记忆、6 篇 ADR 文档、pytest 异步测试 |

---

## 核心亮点

### 1. Agent 引擎：借力 langgraph，聚焦差异化

**技术决策**：不手写 Agent 循环，选择 langgraph 的 `create_react_agent` 获得：
- 自动 ReAct 工具编排（ToolNode 管理 tool_calling 循环）
- 对话状态自动持久化（SqliteSaver checkpoint，无需手动序列化）
- 可配置递归限制（防止 Agent 死循环）

**自建价值**：
- 在 langgraph 之上构建 `AgentLoop`，设计回调机制解耦 Agent 内核与外部消费者
- 流式 + 非流式双模式：`run()` 用于子 Agent 快速返回，`run_stream()` 用于主循环实时交互

### 2. 三层记忆系统：同一个"记忆"词语，三个不同问题

| 层级 | 问题 | 方案 | 关键技术点 |
|------|------|------|-----------|
| 短期记忆 | 对话历史持久化 | SqliteSaver checkpoint | langgraph 内置，按 thread_id 索引，零额外代码 |
| Token 预算 | 上下文窗口有限 | 自研 TokenBudgeter | 超限→LLM 生成摘要→`update_state()` 精确替换，非简单截断 |
| 长期记忆 | 跨会话知识积累 | 文件+SQLite 双写 | LLM 可通过 memory_save/recall/forget 工具自主管理，>20条自动聚合 |

**TokenBudgeter 设计精妙之处**：
- 不让 LLM 丢失语义信息（摘要 vs 截断），保留最近对话完整性
- 压缩失败时静默降级，不阻塞主流程
- 两个阈值（WARN 4000 / COMPACT 8000）渐进式处理

### 3. 权限系统：工具包装模式

**核心设计**：将工具按风险分三级（READ / WRITE / DANGER），权限检查不是中间件——而是把原始工具**包装成新的 StructuredTool**。

**为什么这个设计好**：
- langgraph 视角：一个普通工具，完全透明，不侵入框架内部
- 被拒时：返回自然语言"权限被拒，请尝试其他方法"，而非抛出系统错误
- 支持 `/allow <tool>:<pattern>` 做规则级白名单管理（fnmatch 匹配）
- 三种确认模式：`y`（单次）/ `a`（会话内记住）/ `n`（拒绝）

### 4. MCP 协议集成：动态 Schema 适配

- stdio 连接外部 MCP Server
- `json_schema_to_pydantic_model()` 将 JSON Schema 动态转为 Pydantic Model（`create_model()`）
- `MCPToolAdapter` 封装为 langgraph StructuredTool
- 多 Server 并行连接（`asyncio.gather`），单个失败不阻塞启动
- 工具名自动加 `mcp_{server}_{tool}` 前缀避免冲突

### 5. 子 Agent 编排

- 三种子 Agent：探索（只读文件）、研究（仅网络）、编码（完整能力）
- 受限工具集 = 更安全（子 Agent 不能调用 task/memory 工具，防止递归失控）
- 独立上下文不污染主对话（无 checkpoint，每个子 Agent 独立运行）
- `SubagentRunner.run_parallel()` 并行执行多个子 Agent

### 6. 工具防御性设计

| 工具 | 防御措施 | 防止的问题 |
|------|---------|-----------|
| Edit | old_string 必须唯一匹配（0 或 >1 均拒绝） | LLM 的 typo / 歧义编辑 |
| Bash | 120s 超时，100KB 输出截断（保留头尾） | 脚本死循环 / 输出爆炸 |
| Read | NULL byte 二进制检测 | 误读二进制文件乱码 |
| Grep | 自动跳过二进制，250 条结果硬上限 | 结果溢出上下文窗口 |

### 7. 工程素养

- **Frozen dataclass Config 单例**：不可变 = 线程安全
- **Type hints 全覆盖**
- **6 篇 ADR 风格文档**：记录"做了什么 + 为什么这样做"
- **pytest + pytest-asyncio** 异步测试支持
- **依赖极简**：langgraph + langchain + httpx + mcp + pytest，无臃肿框架

---

## 技术架构

```
agent/          Agent 引擎（langgraph ReAct）
  ├── agent_loop.py      核心循环 + 流式/非流式双模式
  ├── token_budgeter.py  Token 监控 + LLM 摘要自动压缩
  ├── system_prompt.py   中文 System Prompt + 动态上下文
  ├── context_manager.py 滑动窗口 + 增量摘要（辅助方案）
  └── subagent.py        子 Agent 系统（探索/研究/编码）

tools/          工具系统（12 内置 + MCP）
  ├── tool_base.py       工具结果数据结构
  ├── tool_registry.py   工具注册表
  ├── permission.py      三级权限 + 工具包装 + 白名单
  ├── tool_read.py       文件读取（二进制检测，分页）
  ├── tool_write.py      文件写入（自动建父目录）
  ├── tool_edit.py       精确替换（唯一匹配校验）
  ├── tool_bash.py       Shell 执行（超时+截断）
  ├── tool_grep.py       正则搜索（二进制跳过+上限）
  ├── tool_glob.py       文件匹配（mtime 排序）
  ├── tool_web_fetch.py  HTTP 获取+HTML转文本
  ├── tool_todo_write.py 任务列表管理
  └── tool_task.py       子 Agent 派生

memory/         长期记忆（文件+SQLite 双写）
  ├── memory_manager.py   CRUD + 索引重建 + 聚合触发
  └── memory_tools.py     LLM 可调用工具（save/recall/forget）

mcp/            MCP 协议集成
  ├── client.py           stdio 连接管理 + 多 Server 并行
  └── tool_adapter.py     JSON Schema → Pydantic → StructuredTool

storage/        持久化
  ├── session_store.py    会话元数据 + SqliteSaver checkpoint
  └── sqlite_store.py     线程安全 SQLite（对话+记忆双写）
```

---

## 面试核心叙事

- **从 0 到 1 的完整交付**：独立完成架构设计 → 编码 → 测试 → 文档，全链路
- **不做 demo 做工程**：三层记忆（每个层级不同的技术方案）、权限系统（包装模式）、子 Agent（安全边界 + 并行编排）、MCP 协议（动态 Schema 适配）
- **懂原理更懂取舍**：选择 langgraph 而非手写循环（借力成熟框架），选择 SqliteSaver 而非自建存储（零额外代码），选择 LLM 摘要而非粗暴截断（保留语义）——知道什么时候该自己写，什么时候该借力
- **AI Agent 全栈能力**：Agent 编排（ReAct）+ 工具设计（12 内置 + 防御性编程）+ 记忆系统（三层）+ 模型集成（provider-agnostic）+ MCP 协议，覆盖 Agent 开发完整链路

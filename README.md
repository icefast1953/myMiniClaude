# miniClaude

仿造 Claude Code 的轻量级 AI 编程助手。

## MVP 核心能力

1. **对话式 Agent 循环** — 用户输入 → LLM 响应（支持 tool use）→ 执行工具 → 返回结果 → 继续循环
2. **基础工具集** — 文件读写（Read/Write/Edit）、Shell 执行（Bash）、代码搜索（Grep/Glob）
3. **CLI 交互界面** — 终端中的 REPL 式交互

## 技术栈

- Python >= 3.13
- 待定

## 后续扩展

- [ ] 权限控制系统
- [ ] MCP 协议支持
- [ ] 子代理（Subagent）
- [ ] 记忆系统
- [ ] 更多工具支持

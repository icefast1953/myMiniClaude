# miniClaude

仿造 Claude Code 的轻量级 AI 编程助手。

## MVP 核心能力

1. **对话式 Agent 循环**
   - 流程：用户输入 → LLM 响应（支持 tool use）→ 执行工具 → 工具结果追加到消息列表 → 继续循环
   - 退出条件：LLM 返回纯文本（无 tool_call）/ 达到最大轮次上限 / 用户中断
   - 消息管理：每轮工具结果追加到上下文，LLM 可"看到"执行历史
2. **基础工具集** — 统一的 `BaseTool` 抽象 + `ToolRegistry` 注册中心
   - 工具定义：`name` + `description` + `parameters`(JSON Schema) + `execute()`
   - MVP 工具：Read、Write、Edit、Bash、Grep、Glob
3. **CLI 交互界面** — 基于 `rich` 库的 REPL 交互
   - 流式 Markdown 渲染
   - 思考中 Spinner 状态
   - 彩色区分角色（用户/助手/工具调用）
   - 升级到 Textual TUI → 后续扩展

## 技术栈

- Python >= 3.13
- **LLM 后端**：多后端支持，首期集成 DeepSeek API
  - **架构**：内部统一 OpenAI tool call 格式，各后端通过 Adapter 转换
    - `LLMBackend (ABC)` → `DeepSeekBackend` / `AnthropicBackend` / `OpenAICompatBackend`
- **CLI**：`rich` 库（流式 Markdown 渲染）
- **配置**：`python-dotenv` + `Config` 数据类，优先级：.env > 环境变量 > 默认值
  - Anthropic API（后续）
  - 其他 OpenAI 兼容 API（后续）

## 设计决策

- System Prompt：中文角色定义 + 工具使用规则 + 代码规范 + 回复风格，动态信息通过首条 user message 注入
- 流式输出：LLM 响应通过 SSE/stream 逐 token 输出，`rich` 实时渲染 Markdown
- 项目结构：模块文档集中在根目录 `docs/`，每个模块一个文档
- 错误处理：LLM 层指数退避重试（3次），工具层统一返回 `ToolResult(success, error)` 不抛异常
- 测试：`pytest` 单元测试（每个工具、Config）+ 集成测试（Agent 循环 + Mock LLM），核心路径必测

## 后续扩展

- [ ] 权限控制系统
- [ ] 升级到 Textual TUI 全终端界面
- [ ] MCP 协议支持
- [ ] 子代理（Subagent）
- [ ] 记忆系统
- [ ] 更多工具支持

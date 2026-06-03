# Agent 自我纠错 — 设计文档

> 方向二：Self-Correction Loop | 状态：设计完成，待实现
> 最后更新：2026-06-03

## 一、问题定义

Agent 调用工具前没有"刹车"机制，很多错误可以提前拦截而非等执行完才发现。在工具调用 → 实际执行的间隙插入一个轻量自检层。

## 二、架构概览

```
Agent 准备调用工具
       ↓
  ┌─────────────────┐
  │  自检层（纯规则） │
  ├─────────────────┤
  │ 规则引擎（毫秒）  │ ← 格式、权限、逻辑矛盾
  └──────┬──────────┘
         ↓
    通过 → 执行工具
    拦截 → 注入纠正提示 → Agent 调整 → 重新生成调用
```

### Hook 点：独立中间件层

```
main.py:
  raw = [tool_read, tool_write, ...]
  raw = [self_correct_wrap(t, corrector) for t in raw]  # 第1层：自检
  tools = [wrap_tool_with_permission(t, perm, ...) for t in raw]  # 第2层：权限
```

自检和权限关注点分离，独立演进。子代理也复用同一套自检包装。

### 核心设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Hook 点 | 独立中间件层（main.py 在权限包装之前） | 关注点分离，子代理复用 |
| 状态存储 | 内存 dict（CorrectionState） | 零延迟，会话级生命周期合理 |
| 拦截模式 | 三级分级：🔴自动修复 → 🟡硬拦截 → 🔵软建议 | 确定性错误自动修，逻辑可疑拦截，策略优化提示 |
| 规则组织 | 类继承（BaseRule → 具体规则） | 元数据承载、可单测、和项目风格一致 |
| MVP 范围 | 纯规则引擎，6 条规则 | 80% 确定性错误全部可用规则覆盖 |
| 轻量模型 | MVP 不接入，架构预留接口 | 延迟/成本/复杂度，MVP 收益不明显 |

## 三、文件结构

```
miniclaude/agent/
├── self_correction/              # 新目录
│   ├── __init__.py               # 导出 SelfCorrector, wrap_tool_with_correction
│   ├── base.py                   # BaseRule / CheckResult / CorrectionState / ReadRecord
│   ├── engine.py                 # SelfCorrector 主类 + 状态管理 + 检查循环
│   └── rules/                    # 规则实现
│       ├── __init__.py
│       ├── edit_without_read.py      # 🟡 规则 3
│       ├── strip_line_prefix.py      # 🔴 规则 1
│       ├── file_path_absolute.py     # 🔴 规则 2
│       ├── glob_without_grep.py      # 🟡 规则 4
│       ├── sequential_read_spam.py   # 🔵 规则 5
│       └── bash_dangerous.py         # 🔵 规则 6
```

### 职责划分

- **`base.py`**：纯数据类，零依赖 — `CheckResult`, `CorrectionState`, `ReadRecord`, `BaseRule`
- **`engine.py`**：`SelfCorrector` — 加载规则、管理状态、执行检查循环、事后更新状态
- **`rules/*.py`**：每条规则一个文件，继承 `BaseRule`，实现 `check()` 方法

## 四、核心数据结构

### CheckResult

```python
@dataclass
class CheckResult:
    severity: str           # "🔴" | "🟡" | "🔵"
    block: bool             # True = 硬拦截, False = 软建议
    message: str            # 给 Agent 看的纠正提示
    corrected_kwargs: dict | None = None  # 自动修复后的参数（None = 不修改）
```

### CorrectionState

```python
@dataclass
class CorrectionState:
    # 规则 3 (EditWithoutRead): 记录 Agent 读过哪些文件
    files_read: set[str] = field(default_factory=set)

    # 规则 4+5: 最近的读取操作历史（最多 10 条）
    read_history: list[ReadRecord] = field(default_factory=list)

    # 规则 4: Agent 最近一次 glob 返回的文件列表
    last_glob_files: list[str] = field(default_factory=list)

@dataclass
class ReadRecord:
    tool: str              # "read" | "grep" | "glob"
    file_path: str         # 目标文件路径
    content_snippet: str   # 读取内容前 200 字符（关键词匹配用）
    timestamp: float       # time.time()
```

### BaseRule

```python
class BaseRule(ABC):
    name: str              # 规则名称（类名 snake_case）
    severity: str          # "🔴" | "🟡" | "🔵"
    description: str       # 一句话描述
    applicable_tools: set[str]  # 适用的工具名集合

    @abstractmethod
    async def check(
        self,
        tool_name: str,
        kwargs: dict,
        state: CorrectionState,
    ) -> CheckResult | None:
        """返回 CheckResult = 有问题；返回 None = 通过。"""
        ...
```

## 五、MVP 规则清单（6 条）

### 🔴 确定错误 — 硬拦截 + 自动修复

| # | 规则名 | 文件 | 检测条件 | 处理 |
|---|--------|------|---------|------|
| 1 | `StripLinePrefix` | `strip_line_prefix.py` | Edit 的 `old_string` 每行以 `\s*\d+\t` 开头 | 自动剥离行号前缀，`corrected_kwargs` 带修正值 |
| 2 | `FilePathAbsolute` | `file_path_absolute.py` | file_path 参数是相对路径（`../foo`、`./bar`） | 自动 `os.path.abspath()` 解析 |

### 🟡 逻辑可疑 — 硬拦截 + 提示

| # | 规则名 | 文件 | 检测条件 | 处理 |
|---|--------|------|---------|------|
| 3 | `EditWithoutRead` | `edit_without_read.py` | 调用 edit/write 的文件路径不在 `state.files_read` 中 | 拦截，返回 "从未读取过 {path}。请先用 read 工具查看文件内容。" |
| 4 | `GlobWithoutGrep` | `glob_without_grep.py` | Agent 先 glob 到文件列表，然后逐个 read ≥3 个文件（这些文件都在 `last_glob_files` 中） | 第 4 个 read 时拦截，建议用 grep |

### 🔵 策略优化 — 软建议（不拦截）

| # | 规则名 | 文件 | 检测条件 | 处理 |
|---|--------|------|---------|------|
| 5 | `SequentialReadSpam` | `sequential_read_spam.py` | 连续 ≥5 次 read 不同文件，内容含相同关键词 | 工具正常执行，返回结果末尾追加 "💡 建议：你已连续读取 {n} 个文件，考虑使用 grep 搜索共同关键词 {keywords}" |
| 6 | `BashDangerousPattern` | `bash_dangerous.py` | bash 命令匹配危险模式（`rm -rf /`、`git push --force`、`DROP TABLE` 等） | 工具正常执行，返回结果末尾追加 "⚠️ 警告：该命令包含危险操作 {matched_pattern}" |

## 六、SelfCorrector 执行流程

```python
class SelfCorrector:
    def __init__(self):
        self._rules: list[BaseRule] = []
        self._state: CorrectionState = CorrectionState()
        self._pending_warnings: list[str] = []

    def register(self, rule: BaseRule): ...

    async def check(self, tool_name: str, kwargs: dict) -> tuple[bool, dict, str | None]:
        """
        返回值: (should_proceed, modified_kwargs, rejection_message)
        - should_proceed=True → 执行工具（kwargs 可能已被修正）
        - should_proceed=False → 不执行，返回 rejection_message
        """
        for rule in self._rules:
            if tool_name not in rule.applicable_tools:
                continue
            result = await rule.check(tool_name, kwargs, self._state)
            if result is None:
                continue
            if result.corrected_kwargs:
                kwargs = result.corrected_kwargs
            if result.block:
                return (False, kwargs, result.message)
            else:
                self._pending_warnings.append(result.message)
        return (True, kwargs, None)

    async def record(self, tool_name: str, kwargs: dict, result: str):
        """工具执行成功后更新状态（事后记录）。"""
        # 更新 files_read, read_history, last_glob_files

    def pop_warnings(self) -> list[str]:
        """取出并清空待追加的软建议。"""
        ...
```

### 关键设计：check() 和 record() 分两步

- `check()` 在工具执行**前**：读状态，判断是否拦截
- `record()` 在工具执行**后**：写状态，记录执行结果

这样自检不需要知道工具内部逻辑，只需要事后更新追踪数据。

## 七、wrap_tool_with_correction 实现

```python
def wrap_tool_with_correction(tool: StructuredTool, corrector: SelfCorrector) -> StructuredTool:
    """包装单个工具，注入自检层。"""

    async def guarded_func(**kwargs) -> str:
        # 1. 执行前自检
        should_proceed, modified_kwargs, rejection = await corrector.check(tool.name, kwargs)
        if not should_proceed:
            return rejection  # Agent 看到错误消息，自行调整

        # 2. 执行原始工具
        result = await tool.ainvoke(modified_kwargs)

        # 3. 执行后记录状态
        await corrector.record(tool.name, modified_kwargs, result)

        # 4. 追加软建议
        warnings = corrector.pop_warnings()
        if warnings:
            result += "\n\n" + "\n".join(warnings)

        return result

    return StructuredTool.from_function(
        coroutine=guarded_func,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
    )
```

## 八、与现有系统的集成

### main.py 改动

```python
# 新增导入
from miniclaude.agent.self_correction import SelfCorrector, wrap_tool_with_correction

# 初始化自检引擎
corrector = SelfCorrector()
corrector.register_all()  # 加载 6 条规则

# 工具包装链
raw = [tool_read, tool_write, tool_edit, ...]
raw = [wrap_tool_with_correction(t, corrector) for t in raw]  # 第1层
tools = [wrap_tool_with_permission(t, perm, _ask(console)) for t in raw]  # 第2层
```

### 子代理接入

子代理也需要自检。在 SubagentRunner 初始化时传入自检包装后的工具，或 SubagentRunner 自身做一层包装。

### 不影响的模块

- `token_budgeter.py` — Token 管理不变
- `task_classifier.py` — 任务分类不变
- `compressor.py` — 压缩引擎不变
- `agent_loop.py` — Agent 循环不变（自检对 langgraph 透明）

## 九、测试计划

### 单元测试（每规则独立）

| 规则 | 测试场景 |
|------|---------|
| StripLinePrefix | 带行号前缀 / 不带前缀 / 空字符串 / 多行混合 |
| FilePathAbsolute | `../foo` / `./bar` / 绝对路径 / Windows 盘符 |
| EditWithoutRead | 已读 → 通过 / 未读 → 拦截 / write 同理 |
| GlobWithoutGrep | glob 3 文件 + read 3 次 → 拦截第 4 次 / 不相关 read → 通过 |
| SequentialReadSpam | 5 次连续 read → 软建议 / 4 次 → 无 / grep 中断 → 重置 |
| BashDangerousPattern | `rm -rf /` 命中 / `ls -la` 不命中 / 空命令 / 多模式匹配 |

### 集成测试

- 工具包装链正确性：原始工具功能不受影响（read/write/edit 端到端）
- 状态追踪正确性：read 后 files_read 更新，glob 后 last_glob_files 更新
- 拦截消息格式：Agent 能理解并据此调整行为（手工验证）
- 子代理自检覆盖：task 工具派出的子代理也受自检约束

### 性能基准

- 每条规则 `check()` 平均耗时 < 1ms
- 6 条规则全部执行 < 5ms
- 工具执行延迟增加 < 1%（除了需要 I/O 的工具本身延迟）

## 十、与 README 拓展区的对应

| README 描述 | 实现对应 |
|-------------|---------|
| "逻辑合理性：想 Edit foo.py 但从未 Read 过" | 规则 3 `EditWithoutRead` |
| "参数正确性：Edit 的 old_string 带了行号前缀" | 规则 1 `StripLinePrefix` |
| "策略优化：连读 5 个文件做同模式匹配" | 规则 4 `GlobWithoutGrep` + 规则 5 `SequentialReadSpam` |
| "规则引擎为主（80%）+ 轻量模型为辅（可选）" | MVP 纯规则，架构预留 ModelRule 接口 |
| "核心路径零额外延迟" | 内存 dict 状态 + 纯 CPU 规则匹配 |

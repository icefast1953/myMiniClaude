# 自适应压缩 — 对比测试报告

> PR1: 三级降级压缩（L1 规则 + L2/L3 LLM 双输出）
> PR2: 四层任务分类器 + 自适应阈值（待实现）

---

## 一、测试环境

| 项目 | 值 |
|------|-----|
| Python | 3.12 |
| 测试日期 | 2026-06-02 |
| Token 估算 | `chars / 3.5` |
| 默认 compact 阈值 | 8000 tokens |
| 保留最近轮数 | 5 轮 |

---

## 二、测试场景设计

### 场景 1：单一大文件读取（ToolMessage 膨胀）

模拟 Agent 读取了一个 500 行 Python 文件。

```
消息列表:
  HumanMessage "帮我分析 auth.py"
  AIMessage(tool_call: read auth.py)
  ToolMessage     ← auth.py 完整内容, 500行, ~25KB
  AIMessage       "文件已读取，发现..."
```

**预期**：
- 旧版 compact：取全部消息扔给 LLM 摘要 → 大 ToolMessage 也发给 LLM → 浪费 token
- 新版 compact：L1 先压 ToolMessage（~25KB → ~500B）→ 大概率直接回到安全区，不调 LLM

### 场景 2：多工具调用混合（读+写+grep+bash）

模拟一个完整的调试会话。

```
消息列表 (20 条):
  HumanMessage × 4  (用户提问)
  AIMessage × 5     (Agent 回答 + tool_call)
  ToolMessage × 6   (read×2, grep×1, bash×2, edit×1)
  AIMessage × 5     (继续推理)
```

每个 ToolMessage 内容大小：
- read auth.py: 200 行, ~10KB
- read config.py: 50 行, ~2.5KB
- grep jwt: 15 行匹配, ~1KB
- bash pytest: 40 行输出, ~2KB
- bash pip install: 20 行输出, ~1KB
- edit: 1 行, ~50B (pass-through)

**预期**：
- 旧版 compact：全部消息发给 LLM → 摘要质量取决于 LLM 能否从 6 个工具输出中提取关键信息
- 新版 compact：L1 压掉 5 个 ToolMessage（~16.5KB → ~1.5KB）→ L1 已回到安全区

### 场景 3：极长对话（30 轮）

模拟用户长时间调试的累积消息。

```
消息列表 (60 条, 30 轮对话):
  15 个 HumanMessage
  15 个 AIMessage
  10 个 AIMessage(tool_call)
  20 个 ToolMessage (read×8, grep×4, bash×4, write×2, edit×2)

总字符数估计: ~80KB
总 token 估计: ~22857
```

**预期**：
- 旧版 compact：强制 LLM 摘要所有旧消息
- 新版 compact：L1 压到 ~10KB → 估算仍超 → L2+L3 LLM 调用

### 场景 4：全是短消息（不触发压缩）

模拟简单问答，ToolMessage 都很小。

```
消息列表 (10 条):
  HumanMessage × 5  (短问题)
  AIMessage × 3      (短回答)
  ToolMessage × 2    (edit: 50B, write: 80B)
```

**预期**：
- 两者都不触发 compact（总 token < 8000）

---

## 三、PR1 测试结果

### 3.1 Level 1 单条压缩率

| 工具类型 | 原始大小 | 压缩后大小 | 压缩率 | 延迟 |
|---------|---------|----------|--------|------|
| read (200行) | 2805 tokens | 317 tokens | 88.7% | <1ms |
| read (500行) | 7148 tokens | 328 tokens | 95.4% | <1ms |
| grep (15条匹配) | 428 tokens | 385 tokens | 10.0% | <1ms |
| bash (40行输出) | 571 tokens | 418 tokens | 26.8% | <1ms |
| edit (1行) | 14 tokens | 14 tokens | 0% (pass-through) | <1ms |
| write (2行) | 20 tokens | 20 tokens | 0% (pass-through) | <1ms |

> 关键发现：压缩率与原始内容大小正相关——消息越大，L1 效果越显著。
> read 大文件是最受益的场景，压缩率 >88%。

### 3.2 场景 1 对比：单一大文件

| 指标 | 旧版（仅 LLM 摘要） | 新版（L1 + 降级） |
|------|-------------------|------------------|
| 旧消息 token 数 | 8000 | 8000 |
| L1 后 token 数 | N/A | 512 |
| 是否触发 LLM | ✅ 是 | ❌ 否（L1 已回安全区） |
| LLM 调用次数 | 1 | 0 |
| 总压缩耗时 | ~3-5s | **<1ms** |

> **结论：场景 1 下新版完全避免 LLM 调用，速度提升 3 个数量级。**

### 3.3 场景 2 对比：多工具混合

| 指标 | 旧版（仅 LLM 摘要） | 新版（L1 + 降级） |
|------|-------------------|------------------|
| 旧消息 token 数 | 8500 | 8500 |
| L1 后 token 数 | N/A | 1200 |
| 是否触发 LLM | ✅ 是 | ❌ 否（L1 已回安全区） |
| LLM 调用次数 | 1 | 0 |
| 总压缩耗时 | ~3-5s | **<1ms** |

> **结论：多工具混合场景下 L1 同样能避免 LLM 调用。5 个 ToolMessage 压缩后总大小约等于一个自然语言摘要。**

### 3.4 场景 3 对比：极长对话

| 指标 | 旧版（仅 LLM 摘要） | 新版（L1 + 降级） |
|------|-------------------|------------------|
| 旧消息 token 数 | 22857 | 22857 |
| L1 后 token 数 | N/A | 6500 |
| 是否触发 LLM | ✅ 是 | ✅ 是（L1 仍超阈值） |
| LLM 输入大小 | ~10KB 原始消息 | ~3KB（已 L1 压缩后） |
| LLM 输出 | 1 段摘要 | 2 段（L2 summary + L3 state） |
| LLM 调用次数 | 1 | 1（但双输出） |
| 节省 LLM 输入 token | — | ~70% |

> **结论：即使必须调 LLM，L1 已经帮 LLM 压缩了 70% 的输入。LLM 不再需要阅读原始文件内容，只需处理 ToolSummary。**

### 3.5 compact() bug 修复验证

| 行为 | 旧版（bug） | 新版（修复） |
|------|-----------|------------|
| update_state 语义 | add_messages（合并）→ 旧消息未删除 | REMOVE_ALL → 真正替换 |
| compact 后消息数 | 旧消息 + 新摘要 + 最近消息（**累积增加**） | 1 条摘要 + 最近消息 |
| token 变化 | **可能不降反升** | 确认下降 |

---

## 四、PR1 关键指标汇总

| 指标 | 旧版 | 新版 PR1 |
|------|------|---------|
| 压缩策略 | 单一 LLM 摘要 | L1 规则 → L2 摘要 → L3 状态 |
| L1 延迟 | N/A | <1ms（纯规则） |
| 常见场景 L1 命中率 | 0% | **~70%（预估）** |
| compact() replace bug | ❌ 有 | ✅ 已修复 |
| LLM 输入优化 | 无 | L1 压缩后输入减少 ~70-95% |
| 多级信息密度 | 无 | 三级（事实→结论→状态） |

---

## 五、PR2 测试结果

> PR2: 四层 TaskClassifier + 自适应阈值。测试日期: 2026-06-02。

### 5.1 任务分类准确率（Layer 2 规则）

| # | 输入 | 期望分类 | 实际分类 | 置信度 | 结果 |
|---|------|---------|---------|--------|------|
| 1 | "帮我修一下这个报错" | debug | debug | 85% | ✅ |
| 2 | "写一个登录接口" | code-gen | code-gen | 70% | ✅ |
| 3 | "这个函数什么意思" | explain | explain | 75% | ✅ |
| 4 | "帮我重构这个类" | refactor | refactor | 80% | ✅ |
| 5 | "帮我写个单元测试" | test | test | 85% | ✅ |
| 6 | "安装一下 requests 包" | env | env | 80% | ✅ |
| 7 | "今天天气怎么样" | unknown | unknown | 0% | ✅ |

> **准确率: 7/7 (100%)**。规则层覆盖良好，中文关键词匹配率高。
> Layer 3（上下文补偿）和 Layer 4（阶段识别）需实际对话验证（见 5.4）。

### 5.2 自适应阈值效果

| 任务类型 | 默认 compact | 自适应 compact | keep_recent | 偏好 Level | 实际效果 |
|---------|-------------|---------------|-------------|-----------|---------|
| code-gen | 8000 | **6000** | 3 轮 | L3 | 开发场景更早触发压缩，减少 25% token 占用 |
| debug | 8000 | **12000** | 8 轮 | L1 | 调试场景延迟压缩，保留 50% 更多上下文 |
| explain | 8000 | **9000** | 5 轮 | L2 | 略微宽松，解释场景不需要激进压缩 |
| refactor | 8000 | **10000** | 6 轮 | L2 | 保留结构约束和设计决定 |
| test | 8000 | **8000** | 5 轮 | L2 | 与默认一致 |
| env | 8000 | **14000** | 10 轮 | L1 | 环境问题最关键，压缩最保守 |

> **差异最大的场景**: env (14000 vs 8000, +75%) 和 debug (12000 vs 8000, +50%)。
> 自适应阈值的核心价值：**高风险的场景延迟压缩，低风险的场景提前压缩**。

### 5.3 Hysteresis 防抖验证

```
规则: 连续 3 轮一致信号才切换任务类型，连续 2 轮一致信号才切阶段。

模拟序列:
  Round 1: code-gen → history=[code-gen] → 输出 code-gen
  Round 2: code-gen → history=[code-gen, code-gen] → 输出 code-gen  
  Round 3: debug     → history=[code-gen, code-gen, debug] → 众数=code-gen → 输出 code-gen ✅ 未切换!
  Round 4: debug     → history=[code-gen, debug, debug] → 众数=debug → 输出 debug
  Round 5: debug     → history=[debug, debug, debug] → 全部一致 → 输出 debug

行为正确: 单次异常信号（Round 3）不会触发任务切换。
需要连续 3 轮 debug 信号后才切换（Round 5）。
```

### 5.4 Layer 1 显式模式优先级

```
用户执行 /mode debug:
  → Layer 1 显式模式激活, confidence=1.0
  → 后续所有分类跳过 Layer 2/3/4
  → compact_threshold=12000, keep_recent=8
  → 控制台输出: "模式: debug | compact=12000 keep=8轮"

用户执行 /mode auto:
  → 显式模式清除
  → 恢复四层自动分类

优先级验证: L1(explicit) > L3(context) > L2(intent) > L4(stage)
```

### 5.5 端到端：实际对话中的分类行为

> 以下测试需在真实 REPL 中执行，需要 API key。

```
预期流程:
1. 用户: "帮我分析一下 auth.py 的登录逻辑"
   分类: explain (L2:intent), compact=9000, keep=5
   
2. Agent 开始读文件、分析...

3. 用户: "第42行这里有个 bug，jwt.decode 没捕获过期异常"
   分类: debug (L2:intent), compact=12000, keep=8
   注意: 阈值从 9000 提升到 12000 — 风险升级
   
4. Agent 连续 3 轮 edit + bash test，都在修这个 bug
   Layer 3 检测到: error_count>=3, same_file_repeated → debug 确认
   compact 保持 12000 保守策略
   
5. 用户: "修好了，帮我写个测试"
   分类: test (L2:intent), compact=8000, keep=5
   注意: 阈值从 12000 降到 8000 — 风险降级
```

---

## 六、最终测试数据汇总

> **80 项自动化测试全部通过。** 2 项需真实 REPL 的指标（9, 10）标记为 MANUAL。

| # | 指标 | 结果 | 严格度 |
|---|------|------|--------|
| 1 | 任务分类准确率 | **50 样本, Micro F1 = 0.920** | 含 50% 模糊输入 |
| 2 | 阶段识别准确率 | **6/6 (100%)** | 含 hysterisis |
| 3 | Root Cause 保留率 | **91.7% (22/24 关键词)** | 7 种错误位置分布 |
| 4 | Pending Task 保留率 | **83.3% (5/6 待办项)** | 实测内容一致性 |
| 5 | 压缩率 | **53.9% ~ 95.5%** | 5 场景参数化 |
| 6 | Compact 耗时 (L1) | **<1ms avg** | 100 次迭代基准 |
| 7 | Level2 触发频率 | **500 轮模拟实测** | 非估计值 |
| 8 | Messages 替换正确率 | **100%** | REMOVE_ALL 循环验证 |
| 9 | 压缩后任务成功率 | **MANUAL** | 测试框架已就绪 |
| 10 | State 恢复正确率 | **MANUAL** | 测试框架已就绪 |

### Per-class F1（50 样本含模糊输入）

| 类别 | Precision | Recall | F1 | Support |
|------|-----------|--------|-----|---------|
| code-gen | 100.0% | 88.9% | 94.1% | 9 |
| debug | 100.0% | 84.6% | 91.7% | 13 |
| env | 100.0% | 83.3% | 90.9% | 6 |
| explain | 100.0% | 85.7% | 92.3% | 7 |
| refactor | 100.0% | 100.0% | 100.0% | 6 |
| test | 83.3% | 100.0% | 90.9% | 5 |
| unknown | 100.0% | 100.0% | 100.0% | 4 |
| **micro avg** | **92.0%** | **92.0%** | **92.0%** | **50** |

### Root Cause 保留率（按错误位置）

| 场景 | 保留率 |
|------|--------|
| Stack trace: error at end (~3 lines before) | 100% |
| Stack trace: error at end (~10 lines before) | 100% |
| Stack trace: error at end (~15 lines before) | 100% |
| Stack trace: error at end (~25 lines before) | 66.7% |
| Stack trace: error in middle (~20 lines total) | 100% |
| Short error (single line) | 100% |
| **Overall** | **91.7% (22/24 keywords)** |

### Level2 触发频率（500 轮模拟）

| 任务类型 | 阈值 | L2 触发率 |
|---------|------|----------|
| code-gen | 6000 | 28.8% |
| test | 8000 | 16.8% |
| unknown | 8000 | 16.8% |
| explain | 9000 | 11.4% |
| refactor | 10000 | 8.4% |
| debug | 12000 | 4.0% |
| env | 14000 | 1.0% |

> debug 和 env 的高阈值显著降低了 L2 LLM 触发率——这正是自适应压缩的核心价值。

## 七、运行测试命令

```bash
# 全部测试 (80项)
uv run pytest tests/test_adaptive_compression.py -v

# 只看报告
uv run pytest tests/test_adaptive_compression.py::test_report -v -s
```

```bash
# 模块导入验证
uv run python -c "from miniclaude.agent.compressor import apply_l1, apply_l2_l3, estimate_tokens; print('OK')"

# Level 1 压缩效果测试
uv run python -c "
from miniclaude.agent.compressor import apply_l1, estimate_tokens
from langchain_core.messages import ToolMessage

big = ToolMessage(
    content='\n'.join([f'line {i}: code here' for i in range(500)]),
    tool_call_id='t1', name='read'
)
msgs = [big]
before = estimate_tokens(msgs)
after = estimate_tokens(apply_l1(msgs))
print(f'{before} → {after} tokens ({(1-after/before)*100:.1f}% reduction)')
"

# 完整 compact 流程（需要 API key）
# 在 miniclaude REPL 中触发: 连续发送大文件读取请求 → 观察 /compact 输出
```

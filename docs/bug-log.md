# Bug 记录与修复日志

记录 miniClaude 开发过程中发现的 bug、调试过程和解决方案。

---

## Bug 1：输出内容后仍显示"思考中"Spinner

**发现**：LLM 已经开始输出文本，但终端同时显示"思考中..."动画。

**调试**：
1. `on_text` 回调只调用 `console.render_stream(text)`，没隐藏 spinner
2. `on_tool_end` 重新显示了 spinner（等待下一轮 LLM）
3. 但 LLM 返回纯文本时不走 `on_tool_start`，spinner 没人关

**根因**：`on_text` 缺乏 `hide_thinking()` 调用

**修复**：创建 `_on_text` 闭包，首次收到文本时隐藏 spinner

---

## Bug 2：`/help` 报 Rich MarkupError

**发现**：输入 `/help` 后崩溃：
```
rich.errors.MarkupError: closing tag '[/]' at position 36 has nothing to close
```

**调试**：检查 `HELP_TEXT`，发现末尾多了个 `[/]`。`[bold]可用命令:[/]` 已经闭合了 `[bold]`，第二个 `[/]` 变为孤立闭合标签

**根因**：添加 `/allow` 命令说明时误加了多余的 `[/]`

**修复**：删除末尾 `[/]`

---

## Bug 3：`guarded_ainvoke()` 参数数量不匹配

**发现**：glob 工具报错：
```
guarded_ainvoke() takes 1 positional argument but 2 were given
```

**调试**：langgraph 的 `ToolNode` 调用 `tool.ainvoke(input, config)`，传了 2 个参数

**根因**：权限守卫的 `guarded_ainvoke(input_data)` 签名未预留扩展参数

**修复**：改为 `guarded_ainvoke(input_data, *args, **kwargs)`

---

## Bug 4：权限守卫导致 ToolNode 类型校验失败

**发现**：修复 Bug 3 后仍报错：
```
TypeError: Tool bash returned unexpected type: <class 'str'>
```

**调试**：
1. 测试不包装权限守卫的裸工具——正常，字符串被 ToolNode 自动包装为 ToolMessage
2. 确认问题出在 monkey-patch 方式：`object.__setattr__(tool, "ainvoke", guarded_ainvoke)` 破坏了 langgraph 内部工具识别
3. langgraph 的 `ToolNode.__init__` 对工具做 `create_tool()` 二次包装

**尝试过的方案**：

| 尝试 | 方法 | 结果 |
|------|------|------|
| 1 | `object.__setattr__` 替换 `ainvoke` | ❌ 运行时类型错误 |
| 2 | 包装类继承 `BaseTool` | ❌ `_arun` 签名不通用 |
| 3 | 包装类 + `__getattr__` 转发 | ❌ ToolNode 二次包装失败 |

**最终方案**：`StructuredTool.from_function` 创建全新工具实例
```python
def wrap_tool_with_permission(tool, manager, on_ask):
    async def guarded_func(**kwargs) -> str:
        # 权限检查 → 通过后调用原始 tool.ainvoke
        ...
    return StructuredTool.from_function(
        coroutine=guarded_func,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
    )
```

**根因**：monkey-patch 或包装类都会破坏 langgraph 的工具识别。正确做法是用框架工厂方法创建新实例

**教训**：不要 monkey-patch 第三方框架对象；优先用框架提供的工厂方法

---

## 总结

| # | 症状 | 根因 | 修复 | 复杂度 |
|---|------|------|------|--------|
| 1 | Spinner 不消失 | 回调缺状态管理 | `_on_text` 闭包 | 低 |
| 2 | Rich 崩溃 | 多余标记标签 | 删 `[/]` | 低 |
| 3 | 参数不匹配 | 签名未预留 | `*args, **kwargs` | 低 |
| 4 | ToolNode 类型错误 | monkey-patch 破坏框架 | `from_function` | 高 |

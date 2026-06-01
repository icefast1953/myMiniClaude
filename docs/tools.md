# 工具系统文档

## 工具列表

| 工具 | 功能 | 关键参数 |
|------|------|----------|
| `read` | 读取文件（带行号、分页、二进制检测） | `file_path`, `offset`, `limit` |
| `write` | 写入文件（自动创建父目录） | `file_path`, `content` |
| `edit` | 精确字符串替换（唯一性检查） | `file_path`, `old_text`, `new_text` |
| `bash` | 执行 Shell 命令（超时、输出截断） | `command`, `description`, `timeout` |
| `grep` | 正则搜索（glob 过滤、输出模式） | `pattern`, `path`, `glob`, `ignore_case`, `output_mode` |
| `glob` | 文件匹配（修改时间排序） | `pattern`, `path` |

## 添加新工具

```python
from langchain_core.tools import tool

@tool("my_tool")
async def tool_my_tool(param1: str, param2: int = 0) -> str:
    """工具描述（会显示给 LLM）。

    Args:
        param1: 参数说明
        param2: 参数说明（可选）
    """
    try:
        # 工具逻辑
        return "结果"
    except Exception as e:
        return f"错误: {e}"
```

然后在 `main.py` 中注册到工具列表。

## 错误处理约定

- 所有错误以 `错误: ` 开头
- 不抛异常（内部 catch 转字符串）
- LLM 看到错误信息后自行调整策略

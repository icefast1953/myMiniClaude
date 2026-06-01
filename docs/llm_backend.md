# LLM 后端文档

## 当前后端

`langchain_openai.ChatOpenAI` → DeepSeek API

配置（.env）：
```
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

## 添加新后端

### Anthropic Claude

```bash
uv add langchain-anthropic
```

```python
from langchain_anthropic import ChatAnthropic
model = ChatAnthropic(api_key="...", model="claude-sonnet-4-6", streaming=True)
```

### Ollama（本地）

```python
from langchain_ollama import ChatOllama
model = ChatOllama(model="qwen2.5:7b", base_url="http://localhost:11434")
```

### 其他 OpenAI 兼容 API

直接复用 `ChatOpenAI`，修改 `base_url` 即可（如通义千问、GLM 等）。

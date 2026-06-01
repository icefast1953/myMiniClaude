"""WebFetch 工具 —— 获取网页内容并转为纯文本。"""

import re
from html import unescape

import httpx
from langchain_core.tools import tool


@tool("web_fetch")
async def tool_web_fetch(url: str, prompt: str = "") -> str:
    """获取网页内容并转为纯文本。适合查阅文档、阅读文章。

    Args:
        url: 要获取的网页 URL（HTTP 自动升级为 HTTPS）
        prompt: 可选，对获取到的内容进行针对性提问
    """
    try:
        if url.startswith("http://"):
            url = "https://" + url[7:]

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "miniClaude/0.1.0",
                    "Accept": "text/html,*/*",
                },
            )

        if response.status_code >= 400:
            return f"错误: HTTP {response.status_code}: {url}"

        text = _html_to_text(response.text)

        if len(text) > 10000:
            text = text[:10000] + "\n\n... [已截断]"

        result = f"# {url}\n\n{text}"
        if prompt:
            result += f"\n\n---\n请根据以上内容回答: {prompt}"

        return result

    except httpx.TimeoutException:
        return f"错误: 请求超时: {url}"
    except httpx.ConnectError:
        return f"错误: 无法连接: {url}"
    except Exception as e:
        return f"错误: 获取网页时出错: {e}"


def _html_to_text(html: str) -> str:
    """简单 HTML → 纯文本转换。"""
    # 去掉 script/style
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.I)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.I)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    # 块级标签 → 换行
    for tag in ["p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "br"]:
        html = re.sub(rf"</?{tag}[^>]*>", "\n", html, flags=re.I)
    # 去掉剩余标签
    html = re.sub(r"<[^>]+>", "", html)
    text = unescape(html)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)

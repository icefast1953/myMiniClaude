"""MCP 客户端 —— 管理多个 MCP Server 的 stdio 连接。

启动时解析 mcp.json 配置，连接各 Server，拉取工具列表。
连接失败的 Server 不阻塞启动，标记为不可用。
"""

import asyncio
import json
from pathlib import Path

from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession
from mcp.types import Tool as MCPTool
from rich.console import Console


class MCPServerConnection:
    """单个 MCP Server 的连接管理。"""

    def __init__(self, name: str, command: str, args: list[str], env: dict | None = None):
        self.name = name
        self.command = command
        self.args = args
        self.env = env
        self.tools: list[MCPTool] = []
        self._available = False
        self._session: ClientSession | None = None
        self._transport = None

    @property
    def available(self) -> bool:
        return self._available

    async def connect(self) -> bool:
        """建立 stdio 连接并拉取工具列表。"""
        try:
            server_params = {"command": self.command, "args": self.args}
            if self.env:
                server_params["env"] = self.env

            self._transport = stdio_client(server_params)
            read, write = await self._transport.__aenter__()
            self._session = ClientSession(read, write)
            await self._session.__aenter__()
            await self._session.initialize()

            result = await self._session.list_tools()
            self.tools = list(result.tools)
            self._available = True
            return True
        except Exception:
            self._available = False
            return False

    async def call_tool(self, name: str, arguments: dict) -> str:
        """调用 MCP 工具。"""
        if not self._available or not self._session:
            return f"错误: MCP Server '{self.name}' 不可用"

        try:
            result = await self._session.call_tool(name, arguments)
            parts = []
            for item in result.content:
                if hasattr(item, "text"):
                    parts.append(item.text)
            return "\n".join(parts) if parts else str(result)
        except Exception as e:
            return f"错误: MCP 工具调用失败: {e}"

    async def close(self) -> None:
        try:
            if self._session:
                await self._session.__aexit__(None, None, None)
            if self._transport:
                await self._transport.__aexit__(None, None, None)
        except Exception:
            pass


class MCPClient:
    """MCP 客户端管理器。解析 mcp.json，管理所有 Server 连接。"""

    def __init__(self, config_path: str = "mcp.json", console: Console | None = None):
        self._config_path = Path(config_path)
        self._servers: dict[str, MCPServerConnection] = {}
        self._console = console

    def load_config(self) -> list[dict]:
        if not self._config_path.exists():
            return []
        try:
            config = json.loads(self._config_path.read_text())
            return config.get("mcpServers", {})
        except (json.JSONDecodeError, OSError):
            return []

    def parse_servers(self) -> None:
        servers_config = self.load_config()
        for name, cfg in servers_config.items():
            if isinstance(cfg, dict) and "command" in cfg:
                self._servers[name] = MCPServerConnection(
                    name=name,
                    command=cfg["command"],
                    args=cfg.get("args", []),
                    env=cfg.get("env"),
                )

    async def connect_all(self) -> None:
        if not self._servers:
            return

        async def _connect_one(conn: MCPServerConnection):
            ok = await conn.connect()
            if self._console:
                status = "[green]✓[/]" if ok else "[red]✗[/]"
                self._console.print(
                    f"  {status} MCP: {conn.name} "
                    f"({'%d tools' % len(conn.tools) if ok else '连接失败'})"
                )

        await asyncio.gather(*[_connect_one(c) for c in self._servers.values()])

    def get_all_tools(self) -> list[dict]:
        result = []
        for sname, conn in self._servers.items():
            if conn.available:
                for tool in conn.tools:
                    result.append({
                        "server": sname,
                        "name": f"mcp_{sname}_{tool.name}",
                        "description": tool.description or f"MCP tool: {tool.name}",
                        "input_schema": tool.inputSchema,
                        "connection": conn,
                        "original_name": tool.name,
                    })
        return result

    async def close_all(self) -> None:
        await asyncio.gather(*[c.close() for c in self._servers.values()])

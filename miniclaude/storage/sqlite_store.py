"""SQLite 持久化存储 —— 对话记录 + 记忆的 SQLite 后端。

表：
- conversations: 每轮对话（user/assistant/system/tool）
- memories: 跨会话记忆
"""

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class SqliteStore:
    """SQLite 存储适配器。线程安全，自动建表。"""

    def __init__(self, db_path: str = "miniclaude.db"):
        self._db_path = str(Path(db_path).resolve())
        self._local = threading.local()
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_db(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_name TEXT,
                turn_index INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS memories (
                name TEXT PRIMARY KEY,
                description TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                mem_type TEXT NOT NULL DEFAULT 'user',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_conv_session
                ON conversations(session_id, turn_index);
        """)
        self._conn.commit()

    # ---- 对话 ----

    def save_turn(
        self, session_id: str, role: str, content: str,
        tool_name: str | None = None, turn_index: int = 0,
    ) -> int:
        now = datetime.now().isoformat()
        cur = self._conn.execute(
            "INSERT INTO conversations (session_id, role, content, tool_name, turn_index, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, role, content, tool_name, turn_index, now),
        )
        self._conn.commit()
        return cur.lastrowid

    def load_turns(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT role, content, tool_name, turn_index, created_at "
            "FROM conversations WHERE session_id = ? "
            "ORDER BY id DESC LIMIT ?", (session_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_turn_count(self, session_id: str) -> int:
        row = self._conn.execute(
            "SELECT MAX(turn_index) as cnt FROM conversations WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return (row["cnt"] or 0) + 1 if row else 0

    # ---- 记忆 ----

    def save_memory(self, name: str, description: str, content: str, mem_type: str = "user") -> None:
        now = datetime.now().isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO memories (name, description, content, mem_type, updated_at) "
            "VALUES (?, ?, ?, ?, ?)", (name, description, content, mem_type, now),
        )
        self._conn.commit()

    def load_memories(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT name, description, content, mem_type, created_at, updated_at "
            "FROM memories ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_memory(self, name: str) -> bool:
        cur = self._conn.execute("DELETE FROM memories WHERE name = ?", (name,))
        self._conn.commit()
        return cur.rowcount > 0

    def search_memories(self, query: str) -> list[dict[str, Any]]:
        q = f"%{query}%"
        rows = self._conn.execute(
            "SELECT name, description, content, mem_type FROM memories "
            "WHERE name LIKE ? OR description LIKE ? OR content LIKE ? "
            "ORDER BY updated_at DESC", (q, q, q),
        ).fetchall()
        return [dict(r) for r in rows]

    # ----

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def get_stats(self) -> dict[str, Any]:
        conv = self._conn.execute("SELECT COUNT(*) as cnt FROM conversations").fetchone()["cnt"]
        mem = self._conn.execute("SELECT COUNT(*) as cnt FROM memories").fetchone()["cnt"]
        return {"db_path": self._db_path, "conversations": conv, "memories": mem}

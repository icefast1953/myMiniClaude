"""会话管理 —— 会话创建/列表/切换/删除，SqliteSaver checkpoint。"""

import uuid
from datetime import datetime
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


class SessionStore:
    """管理会话生命周期。对话内容由 AsyncSqliteSaver checkpoint 管理。"""

    def __init__(self, db_path: str = "miniclaude.db"):
        self._db_path = str(Path(db_path).resolve())
        self._checkpointer = None
        self._ensure_table()

    async def async_init(self):
        """异步初始化 checkpointer（需要 event loop）。

        保存 context manager 引用防止 GC 回收导致连接关闭。
        """
        self._checkpointer_cm = AsyncSqliteSaver.from_conn_string(self._db_path)
        self._checkpointer = await self._checkpointer_cm.__aenter__()

    @property
    def checkpointer(self):
        if self._checkpointer is None:
            raise RuntimeError("SessionStore.async_init() must be called first")
        return self._checkpointer

    def _ensure_table(self) -> None:
        import sqlite3
        conn = sqlite3.connect(self._db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, title TEXT DEFAULT '',
                turn_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
        conn.close()

    def _conn(self):
        import sqlite3
        c = sqlite3.connect(self._db_path)
        c.row_factory = sqlite3.Row
        return c

    def create(self, title: str = "") -> str:
        sid = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        c = self._conn()
        c.execute("INSERT INTO sessions (id, title) VALUES (?, ?)",
                  (sid, title or "新会话"))
        c.commit(); c.close()
        return sid

    def list(self, limit: int = 20) -> list[dict]:
        c = self._conn()
        rows = c.execute(
            "SELECT id, title, turn_count, created_at, updated_at "
            "FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        c.close()
        return [dict(r) for r in rows]

    def update(self, sid: str, turn_count: int, title: str | None = None) -> None:
        c = self._conn()
        if title:
            c.execute(
                "UPDATE sessions SET turn_count=?, title=?, updated_at=datetime('now') "
                "WHERE id=?", (turn_count, title, sid))
        else:
            c.execute(
                "UPDATE sessions SET turn_count=?, updated_at=datetime('now') "
                "WHERE id=?", (turn_count, sid))
        c.commit(); c.close()

    def delete(self, sid: str) -> bool:
        c = self._conn()
        cur = c.execute("DELETE FROM sessions WHERE id=?", (sid,))
        c.commit()
        ok = cur.rowcount > 0
        c.close()
        if ok:
            try:
                import sqlite3 as _s
                cc = _s.connect(self._db_path)
                cc.execute("DELETE FROM checkpoints WHERE thread_id=?", (sid,))
                cc.execute("DELETE FROM checkpoint_writes WHERE thread_id=?", (sid,))
                cc.commit(); cc.close()
            except Exception:
                pass
        return ok

    def get(self, sid: str) -> dict | None:
        c = self._conn()
        row = c.execute(
            "SELECT id, title, turn_count, created_at, updated_at "
            "FROM sessions WHERE id=?", (sid,)).fetchone()
        c.close()
        return dict(row) if row else None

    def is_new(self, sid: str) -> bool:
        s = self.get(sid)
        return s is not None and s["turn_count"] == 0

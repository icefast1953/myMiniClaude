"""长期记忆管理器 —— 索引文件 MEMORY.md + 自动聚合提示。

memory/
├── MEMORY.md          ← 索引（一行一条）
├── user-prefs.md      ← 具体记忆
└── ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from miniclaude.storage.sqlite_store import SqliteStore

INDEX_FILE = "MEMORY.md"
MAX_INDEX = 20  # 超过此数触发聚合提示


@dataclass
class Memory:
    name: str
    description: str
    content: str
    mem_type: str = "user"

    @property
    def filename(self) -> str:
        return f"{self.name}.md"

    def to_markdown(self) -> str:
        fm = {"name": self.name, "description": self.description,
              "metadata": {"type": self.mem_type}}
        y = yaml.dump(fm, allow_unicode=True, sort_keys=False).strip()
        return f"---\n{y}\n---\n\n{self.content}\n"

    @classmethod
    def from_markdown(cls, text: str) -> Memory | None:
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
        if not m:
            return None
        try:
            meta = yaml.safe_load(m.group(1))
            return cls(name=meta.get("name", ""),
                       description=meta.get("description", ""),
                       content=m.group(2).strip(),
                       mem_type=meta.get("metadata", {}).get("type", "user"))
        except Exception:
            return None


class MemoryManager:
    """长期记忆：索引 + 全文 + 自动聚合。"""

    def __init__(self, memory_dir: str | Path = "memory",
                 db: SqliteStore | None = None):
        self._dir = Path(memory_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._db = db
        self._cache: dict[str, Memory] = {}
        idx = self._dir / INDEX_FILE
        if not idx.exists():
            idx.write_text("", encoding="utf-8")
        self._load_all()

    def _load_all(self) -> None:
        self._cache.clear()
        for f in sorted(self._dir.glob("*.md")):
            if f.name == INDEX_FILE:
                continue
            mem = Memory.from_markdown(f.read_text(encoding="utf-8"))
            if mem:
                self._cache[mem.name] = mem
        if self._db:
            for row in self._db.load_memories():
                if row["name"] not in self._cache:
                    self._cache[row["name"]] = Memory(
                        name=row["name"], description=row["description"],
                        content=row["content"], mem_type=row["mem_type"])

    # ── CRUD ──

    def save(self, name: str, description: str, content: str,
             mem_type: str = "user") -> Memory:
        mem = Memory(name=name, description=description,
                     content=content, mem_type=mem_type)
        (self._dir / mem.filename).write_text(mem.to_markdown(), encoding="utf-8")
        if self._db:
            self._db.save_memory(name, description, content, mem_type)
        self._cache[name] = mem
        self._rebuild_index()
        return mem

    def forget(self, name: str) -> bool:
        fp = self._dir / f"{name}.md"
        ok = False
        if fp.exists():
            fp.unlink(); ok = True
        if self._db:
            ok = self._db.delete_memory(name) or ok
        self._cache.pop(name, None)
        if ok:
            self._rebuild_index()
        return ok

    def recall(self, query: str) -> list[Memory]:
        q = query.lower()
        return [m for m in self._cache.values()
                if q in m.name.lower() or q in m.description.lower()
                or q in m.content.lower()]

    def list_all(self) -> list[Memory]:
        return list(self._cache.values())

    # ── 索引 ──

    def _rebuild_index(self) -> None:
        if not self._cache:
            (self._dir / INDEX_FILE).unlink(missing_ok=True)
            return
        lines = [f"- [{m.name}]({m.filename}) — {m.description}"
                 for m in self._cache.values()]
        (self._dir / INDEX_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def get_index(self) -> str:
        idx = self._dir / INDEX_FILE
        return idx.read_text(encoding="utf-8") if idx.exists() else ""

    def should_aggregate(self) -> bool:
        return len(self._cache) >= MAX_INDEX

    def build_aggregation_prompt(self) -> str:
        if not self._cache:
            return ""
        lines = ["请整理以下记忆，合并相似、删除过时、保留关键信息：\n"]
        for m in self._cache.values():
            lines.append(f"- [{m.name}] {m.description}: {m.content[:200]}")
        return "\n".join(lines)

    # ── 上下文 ──

    def get_context(self) -> str:
        index = self.get_index()
        if not index:
            return ""
        return f"[长期记忆] 共 {len(self._cache)} 条:\n{index}"

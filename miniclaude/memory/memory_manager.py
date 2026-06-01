"""记忆管理器 —— 读写 memory/ 目录下的 markdown 记忆文件。

格式：YAML frontmatter + Markdown 正文。
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Memory:
    """一条记忆。"""
    name: str           # kebab-case slug, 用作文件名
    description: str    # 一行摘要
    content: str        # 正文
    mem_type: str       # user | project | reference

    @property
    def filename(self) -> str:
        return f"{self.name}.md"

    def to_markdown(self) -> str:
        frontmatter = {
            "name": self.name,
            "description": self.description,
            "metadata": {"type": self.mem_type},
        }
        yaml_str = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
        return f"---\n{yaml_str}\n---\n\n{self.content}\n"

    @classmethod
    def from_markdown(cls, text: str) -> "Memory | None":
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
        if not match:
            return None
        try:
            meta = yaml.safe_load(match.group(1))
            return cls(
                name=meta.get("name", ""),
                description=meta.get("description", ""),
                content=match.group(2).strip(),
                mem_type=meta.get("metadata", {}).get("type", "user"),
            )
        except Exception:
            return None


class MemoryManager:
    """管理记忆的读写和搜索。"""

    def __init__(self, memory_dir: str | Path = "memory"):
        self._dir = Path(memory_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Memory] = {}
        self._load_all()

    def _load_all(self) -> None:
        self._cache.clear()
        for f in sorted(self._dir.glob("*.md")):
            mem = Memory.from_markdown(f.read_text(encoding="utf-8"))
            if mem:
                self._cache[mem.name] = mem

    def save(self, name: str, description: str, content: str, mem_type: str = "user") -> Memory:
        mem = Memory(name=name, description=description, content=content, mem_type=mem_type)
        (self._dir / mem.filename).write_text(mem.to_markdown(), encoding="utf-8")
        self._cache[name] = mem
        return mem

    def forget(self, name: str) -> bool:
        filepath = self._dir / f"{name}.md"
        if filepath.exists():
            filepath.unlink()
            self._cache.pop(name, None)
            return True
        return False

    def recall(self, query: str) -> list[Memory]:
        q = query.lower()
        results = []
        for mem in self._cache.values():
            if (q in mem.name.lower()
                or q in mem.description.lower()
                or q in mem.content.lower()):
                results.append(mem)
        return results

    def list_all(self) -> list[Memory]:
        return list(self._cache.values())

    def get_context(self) -> str:
        """生成注入 LLM 上下文的记忆摘要。"""
        if not self._cache:
            return ""
        lines = ["[记忆] 以下是已保存的记忆（仅供参考）:"]
        for mem in self._cache.values():
            lines.append(f"- [{mem.name}] {mem.description}")
        return "\n".join(lines)

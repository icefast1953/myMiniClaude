"""Skill 注册表 —— 从 skills/ 目录加载 Markdown 定义文件。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).parent / "skills"


@dataclass
class Skill:
    name: str
    description: str
    body: str
    skill_type: str = "inject"  # inject | subagent
    tools: list[str] = field(default_factory=list)
    model: str = ""

    @property
    def slash_command(self) -> str:
        return f"/{self.name}"

    def render_help(self) -> str:
        tag = "[子代理]" if self.skill_type == "subagent" else "[注入]"
        return f"  /{self.name:20s} {tag} {self.description}"


class SkillRegistry:
    """管理 skill 的加载和查找。"""

    def __init__(self, skills_dir: Path | None = None):
        self._dir = skills_dir or SKILLS_DIR
        self._skills: dict[str, Skill] = {}
        self._load_all()

    def _load_all(self):
        self._skills.clear()
        if not self._dir.exists():
            self._dir.mkdir(parents=True, exist_ok=True)
            return
        for f in sorted(self._dir.glob("*.md")):
            skill = self._parse(f)
            if skill:
                self._skills[skill.name] = skill

    @staticmethod
    def _parse(path: Path) -> Skill | None:
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
        if not match:
            return None
        try:
            meta = yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            return None
        if not meta or "name" not in meta:
            return None
        return Skill(
            name=meta["name"],
            description=meta.get("description", ""),
            body=match.group(2).strip(),
            skill_type=meta.get("type", "inject"),
            tools=meta.get("tools", []),
            model=meta.get("model", ""),
        )

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_all(self) -> list[Skill]:
        return list(self._skills.values())

    def match_prefix(self, prefix: str) -> Skill | None:
        for name, skill in self._skills.items():
            if name.startswith(prefix):
                return skill
        return None

    @property
    def count(self) -> int:
        return len(self._skills)

    @property
    def skills_dir(self) -> Path:
        return self._dir

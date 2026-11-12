from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Collection

_PACK = Path("skills") / "agora"
_SKIP_DIRS = {"testing-guidance"}
_SKIP_FILES = {"doc-fetching.md"}
_WORD = re.compile(r"\w+")
_TITLE_WEIGHT = 3


@dataclass(frozen=True)
class Topic:
    key: str
    title: str
    path: Path


def _references(root: Path) -> Path:
    return Path(root) / _PACK / "references"


def _title(path: Path) -> str:
    try:
        for line in path.read_text(errors="replace").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        pass
    return path.stem


def list_topics(root: Path) -> list[Topic]:
    refs = _references(root)
    if not refs.is_dir():
        return []
    topics = []
    for path in sorted(refs.rglob("*.md")):
        rel = path.relative_to(refs)
        if rel.parts[0] in _SKIP_DIRS or rel.name in _SKIP_FILES and len(rel.parts) == 1:
            continue
        topics.append(Topic(key=rel.as_posix(), title=_title(path), path=path))
    return topics


def load_topic_text(topic: Topic, budget_chars: int) -> str:
    try:
        body = topic.path.read_text(errors="replace")
    except OSError:
        return ""
    return _cut(f"## {topic.title}\n{body.strip()}", budget_chars)


def core_text(root: Path, budget_chars: int) -> str:
    try:
        text = (Path(root) / _PACK / "SKILL.md").read_text(errors="replace")
    except OSError:
        return ""
    return text[: budget_chars // 3]


def _cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = text[:limit]
    boundary = head.rfind("\n\n")
    return head[:boundary] if boundary > 0 else head


def _score(topic: Topic, words: list[str]) -> int:
    try:
        body = topic.path.read_text(errors="replace").lower()
    except OSError:
        return 0
    title = topic.title.lower()
    return sum(body.count(w) + _TITLE_WEIGHT * title.count(w) for w in words)


def pick_relevant(
    root: Path, query: str, budget_chars: int, exclude: Collection[str] = ()
) -> tuple[str, list[str]]:
    words = [w for w in _WORD.findall(query.lower()) if len(w) >= 4]
    scored = [(_score(t, words), t) for t in list_topics(root) if t.key not in exclude]
    ranked = sorted((pair for pair in scored if pair[0] > 0), key=lambda p: (-p[0], p[1].key))

    parts: list[str] = []
    keys: list[str] = []
    used = 0
    for _, topic in ranked:
        remaining = budget_chars - used
        if remaining <= 0:
            break
        text = load_topic_text(topic, remaining)
        if not text:
            continue
        parts.append(text)
        keys.append(topic.key)
        used += len(text) + 2
    return "\n\n".join(parts), keys

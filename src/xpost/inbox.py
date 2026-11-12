from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

TAG_TO_TYPE = {"linkedin": "agora_news", "event": "event", "built": "build", "note": "build"}

_TAG_LINE = re.compile(r"^\[(\w+)\]\s*(.*)$")
_URL = re.compile(r"https?://\S+")
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class InboxEntry:
    id: str
    tag: str
    text: str
    urls: tuple[str, ...]


def _entry(block: list[str]) -> InboxEntry | None:
    lines = list(block)
    while lines and not lines[0].strip():
        lines.pop(0)
    tag = "note"
    if lines:
        match = _TAG_LINE.match(lines[0].strip())
        if match:
            tag = match.group(1).lower() if match.group(1).lower() in TAG_TO_TYPE else "note"
            lines[0] = match.group(2)
    text = "\n".join(lines).strip()
    if not text:
        return None
    urls = tuple(u.rstrip(").,;]\"'") for u in _URL.findall(text))
    digest = hashlib.sha1(_SPACE.sub(" ", text).encode()).hexdigest()[:12]
    return InboxEntry(id=digest, tag=tag, text=text, urls=urls)


def parse_inbox(text: str) -> list[InboxEntry]:
    blocks: list[list[str]] = [[]]
    for line in text.splitlines():
        if line.strip() == "---":
            blocks.append([])
        else:
            blocks[-1].append(line)
    # Lines starting with '#' in the first block (before any separator) are comments.
    blocks[0] = [line for line in blocks[0] if not line.lstrip().startswith("#")]
    entries = (_entry(block) for block in blocks)
    return [e for e in entries if e is not None]

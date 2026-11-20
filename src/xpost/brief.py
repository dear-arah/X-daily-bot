from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Sequence

from xpost.models import Item

_NON_ALNUM = re.compile(r"[^a-z0-9]")
_BRIEF_GROUPS = ("world",)  # search-index items are unchecked, so they stay out of the context


def build_brief(items: Sequence[Item], now: datetime, max_age_days: int, size: int) -> str:
    cutoff = now - timedelta(days=max_age_days)
    fresh = [
        i for i in items if i.group in _BRIEF_GROUPS and i.published is not None and i.published >= cutoff
    ]
    fresh.sort(key=lambda i: i.published, reverse=True)

    seen: set[str] = set()
    lines: list[str] = []
    for item in fresh:
        key = _NON_ALNUM.sub("", item.title.lower())
        if not key or key in seen:
            continue
        seen.add(key)
        lines.append(f"- {item.published:%Y-%m-%d} · {item.source} · {item.title}")
        if len(lines) >= size:
            break
    return "\n".join(lines)

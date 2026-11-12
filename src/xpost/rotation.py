from __future__ import annotations

from typing import Collection, Sequence

from xpost.models import POST_TYPES


def pick_type(last: str | None, available: Collection[str], order: Sequence[str] = POST_TYPES) -> str | None:
    """Next type after `last` in `order` that has material; `last` itself is the final candidate."""
    start = order.index(last) + 1 if last in order else 0
    for step in range(len(order)):
        candidate = order[(start + step) % len(order)]
        if candidate in available:
            return candidate
    return None

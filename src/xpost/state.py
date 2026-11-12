from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from xpost.models import Draft

_TRACKING_PARAMS = {"fbclid", "gclid", "ref", "ref_src", "mc_cid", "mc_eid"}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.startswith("utm_") and k not in _TRACKING_PARAMS
    )
    return urlunsplit((parts.scheme.lower(), host, parts.path.rstrip("/"), urlencode(query), ""))


class State:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._drafts: list[dict] = self._load()

    def _load(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return []
        drafts = data.get("drafts") if isinstance(data, dict) else None
        if not isinstance(drafts, list):
            return []
        return [d for d in drafts if isinstance(d, dict) and {"date", "type"} <= d.keys()]

    def last_type(self) -> str | None:
        if not self._drafts:
            return None
        latest = max(enumerate(self._drafts), key=lambda pair: (pair[1]["date"], pair[0]))
        return latest[1]["type"]

    def recent_whys(self, n: int = 7) -> list[str]:
        ordered = sorted(enumerate(self._drafts), key=lambda pair: (pair[1]["date"], pair[0]))
        return [d.get("why", "") for _, d in ordered][-n:] if n > 0 else []

    def drafted_today(self, today: date) -> bool:
        return any(d["date"] == today.isoformat() for d in self._drafts)

    def is_seen(self, key: str) -> bool:
        return any(key in d.get("keys", []) for d in self._drafts)

    def record(self, draft: Draft, keys: Sequence[str], today: date) -> None:
        self._drafts.append(
            {"date": today.isoformat(), "type": draft.post_type, "why": draft.why, "keys": list(keys)}
        )

    def prune(self, today: date, days: int = 60) -> None:
        cutoff = (today - timedelta(days=days)).isoformat()
        self._drafts = [d for d in self._drafts if d["date"] >= cutoff]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"drafts": self._drafts}, indent=2, sort_keys=True))

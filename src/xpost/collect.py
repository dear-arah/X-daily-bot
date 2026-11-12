from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone
from typing import Callable, Iterable

import feedparser
import requests

from xpost.models import Item, Source

log = logging.getLogger(__name__)

TEXT_LIMIT = 2000
USER_AGENT = "x-daily-bot/0.1"

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_BARE_VERSION = re.compile(r"^v?\d+(\.\d+)+\S*$")


class FeedError(Exception):
    pass


def _clean(raw: str) -> str:
    text = html.unescape(_TAG.sub(" ", raw))
    return _SPACE.sub(" ", text).strip()[:TEXT_LIMIT]


def _published(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=timezone.utc)


def _body(entry) -> str:
    if entry.get("summary"):
        return entry["summary"]
    content = entry.get("content")
    return content[0].get("value", "") if content else ""


def fetch_feed(source: Source, get: Callable = requests.get, timeout: float = 15) -> list[Item]:
    try:
        response = get(source.url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
    except Exception as exc:
        raise FeedError(f"{source.name}: {exc}") from exc

    parsed = feedparser.parse(response.content)
    items = []
    for entry in parsed.entries:
        link = entry.get("link")
        if not link:
            continue
        title = _clean(entry.get("title", ""))
        publisher = (entry.get("source") or {}).get("title", "")
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -len(f" - {publisher}")]
        if _BARE_VERSION.match(title):
            title = f"{source.name} {title}"
        items.append(
            Item(
                title=title,
                url=link,
                text=_clean(_body(entry)),
                published=_published(entry),
                source=source.name,
                group=source.group,
            )
        )
    if source.must_match:
        needles = [p.lower() for p in source.must_match]
        items = [i for i in items if any(n in f"{i.title} {i.text} {i.url}".lower() for n in needles)]
    return items


def collect_all(sources: Iterable[Source], get: Callable = requests.get) -> list[Item]:
    items: list[Item] = []
    for source in sources:
        if "<" in source.url:
            log.warning("skipping %s: fill in the placeholder in its url", source.name)
            continue
        try:
            items.extend(fetch_feed(source, get=get))
        except FeedError as exc:
            log.warning("skipping feed: %s", exc)
    return items

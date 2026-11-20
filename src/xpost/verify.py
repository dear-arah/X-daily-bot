from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable

import requests

log = logging.getLogger(__name__)

TEXT_LIMIT = 1500
ATTEMPTS = 3
RETRY_PAUSE = 0.7
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; x-daily-bot/0.1)"}
_SPACE = re.compile(r"\s+")
_SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header", "svg", "form"}
_TEXT_TAGS = {"p", "h1", "h2", "h3", "li"}


@dataclass(frozen=True)
class PageCheck:
    status: str  # "ok" (page opened) | "dead" (404/410) | "unknown" (blocked, rate limited, error)
    final_url: str
    text: str


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.paragraphs: list[str] = []
        self._skip = 0
        self._in_title = False
        self._in_text = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (attrs.get("name") or attrs.get("property") or "").lower()
            if name in ("description", "og:description") and not self.description:
                self.description = attrs.get("content") or ""
        elif tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _TEXT_TAGS and not self._skip:
            self._in_text += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag in _TEXT_TAGS and self._in_text:
            self._in_text -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._in_text and not self._skip:
            self.paragraphs.append(data)


def page_text(html: str, limit: int = TEXT_LIMIT) -> str:
    """Title, meta description and the main readable text of a page, collapsed and cut to `limit`."""
    parser = _Extractor()
    try:
        parser.feed(html)
    except Exception:  # malformed markup: use whatever was read
        pass
    parts = [parser.title, parser.description, " ".join(parser.paragraphs)]
    return _SPACE.sub(" ", " ".join(p for p in parts if p.strip())).strip()[:limit]


def _check_once(url: str, get: Callable, timeout: float) -> PageCheck:
    try:
        response = get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
    except Exception as exc:
        log.warning("could not open %s: %s", url, exc)
        return PageCheck("unknown", url, "")
    if response.status_code in (404, 410):
        return PageCheck("dead", url, "")
    if response.status_code >= 400:
        return PageCheck("unknown", url, "")
    final = getattr(response, "url", None) or url
    is_html = "html" in response.headers.get("Content-Type", "").lower()
    return PageCheck("ok", final, page_text(response.text) if is_html else "")


def check_url(
    url: str,
    get: Callable = requests.get,
    timeout: float = 15,
    attempts: int = ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> PageCheck:
    """Open `url` several times. A 404 or 410 on any try means dead: a page that opens only some of the
    time (agora.io does this) gives readers a 404 too, so it is not worth posting. Sites that block bots
    (403, 429) or are briefly down stay "unknown", so a good link is not thrown away over a hiccup."""
    good: PageCheck | None = None
    for attempt in range(attempts):
        if attempt:
            sleep(RETRY_PAUSE)
        result = _check_once(url, get, timeout)
        if result.status == "dead":
            return result
        if result.status == "ok":
            good = good or result
        else:
            return good or result
    return good or PageCheck("unknown", url, "")

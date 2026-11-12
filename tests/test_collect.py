from pathlib import Path

import pytest

from xpost.collect import FeedError, collect_all, fetch_feed
from xpost.models import Source

FIXTURE = Path(__file__).parent / "fixtures" / "feed.xml"


class Resp:
    def __init__(self, content=b"", status=200):
        self.content = content
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")


def _get_ok(url, **kwargs):
    return Resp(FIXTURE.read_bytes())


def test_fetch_feed_parses_entries():
    source = Source("Blog", "https://example.com/feed", "agora")
    items = fetch_feed(source, get=_get_ok)
    assert [i.title for i in items] == ["Voice agents ship & scale", "Blog v1.2.3"]
    assert items[0].url == "https://example.com/a"
    assert items[0].text == "First post body"
    assert items[0].group == "agora"
    assert items[0].published.year == 2026


def test_fetch_feed_raises_feed_error_on_http_error():
    source = Source("Blog", "https://example.com/feed", "world")
    with pytest.raises(FeedError):
        fetch_feed(source, get=lambda url, **kw: Resp(status=500))


def test_collect_all_skips_broken_feed():
    sources = [Source("Bad", "https://bad/feed", "world"), Source("Good", "https://good/feed", "world")]

    def get(url, **kwargs):
        return Resp(status=404) if "bad" in url else Resp(FIXTURE.read_bytes())

    items = collect_all(sources, get=get)
    assert {i.source for i in items} == {"Good"}


def test_placeholder_urls_are_skipped():
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return Resp(FIXTURE.read_bytes())

    sources = [Source("Mine", "https://dev.to/feed/<DEVTO_USERNAME>", "own")]
    assert collect_all(sources, get=get) == []
    assert calls == []

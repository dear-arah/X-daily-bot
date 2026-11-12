from datetime import datetime, timedelta, timezone

from xpost.brief import build_brief
from xpost.models import Item

NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)


def _item(title, days_ago, group="world", source="Src"):
    return Item(title, f"https://x/{title}", "", NOW - timedelta(days=days_ago), source, group)


def test_brief_lists_newest_first_and_limits_size():
    items = [_item("old", 5), _item("newest", 1), _item("mid", 3)]
    brief = build_brief(items, NOW, max_age_days=14, size=2)
    lines = brief.splitlines()
    assert len(lines) == 2
    assert lines[0] == "- 2026-11-12 · Src · newest"
    assert lines[1].endswith("mid")


def test_brief_drops_old_and_duplicate_titles():
    items = [_item("Fresh news!", 1), _item("fresh news", 2), _item("stale", 30)]
    brief = build_brief(items, NOW, max_age_days=14, size=10)
    assert brief.count("\n") == 0
    assert "stale" not in brief


def test_brief_excludes_own_group():
    items = [_item("mine", 1, group="own"), _item("agora thing", 1, group="agora")]
    brief = build_brief(items, NOW, max_age_days=14, size=10)
    assert "mine" not in brief and "agora thing" in brief


def test_brief_empty_when_nothing_qualifies():
    assert build_brief([], NOW, 14, 10) == ""
    assert build_brief([_item("x", 99)], NOW, 14, 10) == ""

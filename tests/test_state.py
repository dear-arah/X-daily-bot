import json
from datetime import date

from xpost.models import Draft
from xpost.state import State, normalize_url


def _draft(post_type="build", why="angle"):
    return Draft(post_type, ("a", "b"), why, ())


def test_missing_file_is_empty_state(tmp_path):
    state = State(tmp_path / "s.json")
    assert state.last_type() is None
    assert state.recent_whys() == []


def test_corrupt_file_is_empty_state(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json")
    assert State(path).last_type() is None


def test_record_then_reload_round_trips(tmp_path):
    path = tmp_path / "s.json"
    state = State(path)
    state.record(_draft("tip", "why one"), ["k1"], date(2026, 11, 13))
    state.save()
    reloaded = State(path)
    assert reloaded.last_type() == "tip"
    assert reloaded.recent_whys() == ["why one"]
    assert json.loads(path.read_text())["drafts"][0]["keys"] == ["k1"]


def test_is_seen_matches_recorded_keys(tmp_path):
    state = State(tmp_path / "s.json")
    state.record(_draft(), ["abc", "topic:rtc/web.md"], date(2026, 11, 13))
    assert state.is_seen("abc") and state.is_seen("topic:rtc/web.md")
    assert not state.is_seen("zzz")


def test_last_type_returns_latest_by_date_then_order(tmp_path):
    state = State(tmp_path / "s.json")
    state.record(_draft("tip"), [], date(2026, 11, 14))
    state.record(_draft("build"), [], date(2026, 11, 13))
    assert state.last_type() == "tip"
    state.record(_draft("event"), [], date(2026, 11, 14))
    assert state.last_type() == "event"


def test_recent_whys_returns_last_n_oldest_first(tmp_path):
    state = State(tmp_path / "s.json")
    for i in range(5):
        state.record(_draft(why=f"w{i}"), [], date(2026, 11, 10 + i))
    assert state.recent_whys(2) == ["w3", "w4"]


def test_drafted_today(tmp_path):
    state = State(tmp_path / "s.json")
    state.record(_draft(), [], date(2026, 11, 13))
    assert state.drafted_today(date(2026, 11, 13))
    assert not state.drafted_today(date(2026, 11, 14))


def test_prune_drops_old_drafts(tmp_path):
    state = State(tmp_path / "s.json")
    state.record(_draft(why="old"), ["old"], date(2026, 8, 1))
    state.record(_draft(why="new"), ["new"], date(2026, 11, 12))
    state.prune(date(2026, 11, 13), days=60)
    assert not state.is_seen("old") and state.is_seen("new")


def test_normalize_url_strips_tracking_params_and_www():
    assert normalize_url("https://www.Example.com/a/?utm_source=x&b=1&fbclid=z#frag") == "https://example.com/a?b=1"

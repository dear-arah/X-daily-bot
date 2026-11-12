from xpost.models import POST_TYPES
from xpost.rotation import pick_type

ALL = set(POST_TYPES)


def test_first_run_starts_at_first_type():
    assert pick_type(None, ALL) == "agora_news"


def test_advances_one_step():
    assert pick_type("agora_news", ALL) == "build"


def test_wraps_around_after_last():
    assert pick_type("event", ALL) == "agora_news"


def test_skips_unavailable_types():
    assert pick_type("agora_news", {"tip", "question"}) == "tip"
    assert pick_type("tip", {"build", "tip"}) == "build"


def test_does_not_repeat_last_unless_only_option():
    assert pick_type("question", {"question", "event"}) == "event"
    assert pick_type("question", {"question"}) == "question"


def test_returns_none_when_nothing_available():
    assert pick_type(None, set()) is None


def test_unknown_last_starts_over():
    assert pick_type("poll", ALL) == "agora_news"


def test_respects_custom_order():
    assert pick_type("tip", ALL, order=("tip", "question")) == "question"

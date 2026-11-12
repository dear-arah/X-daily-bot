import json

import pytest

from xpost.draft import (
    TYPE_BRIEFS,
    DraftError,
    build_messages,
    generate,
    intent_url,
    parse_draft,
    tweet_length,
)
from xpost.llm.providers import AllProvidersFailed
from xpost.models import POST_TYPES


def test_tweet_length_counts_urls_as_23():
    assert tweet_length("hi https://example.com/a/very/long/path?x=1") == 3 + 23


def test_tweet_length_counts_emoji_and_cjk_double():
    assert tweet_length("a😀") == 3
    assert tweet_length("日本") == 4
    assert tweet_length("it’s") == 4  # curly apostrophe is in the single-weight range


def test_intent_url_encodes_reserved_characters():
    url = intent_url("a&b (c)?")
    assert url.startswith("https://x.com/intent/tweet?text=")
    assert url.endswith("a%26b%20%28c%29%3F")


def _raw(variants, why="because"):
    return json.dumps({"variants": variants, "why": why})


def test_parse_draft_reads_json_inside_prose():
    variants, why = parse_draft("Sure! " + _raw(["one", "two"], "reason") + " done", 2)
    assert variants == ("one", "two") and why == "reason"


def test_parse_draft_rejects_wrong_variant_count():
    with pytest.raises(DraftError):
        parse_draft(_raw(["only one"]), 2)


def test_parse_draft_rejects_missing_why():
    with pytest.raises(DraftError):
        parse_draft(json.dumps({"variants": ["a", "b"]}), 2)


def test_parse_draft_rejects_non_json():
    with pytest.raises(DraftError):
        parse_draft("no json here", 2)


class FakeChain:
    def __init__(self, raws):
        self.raws = list(raws)
        self.calls = []

    def complete(self, system, user, parse=None, temperature=0.2):
        self.calls.append((system, user, temperature))
        raw = self.raws.pop(0)
        return parse(raw) if parse else raw


def test_generate_returns_valid_draft_with_creative_temperature():
    chain = FakeChain([_raw(["short one", "short two"], "why")])
    draft = generate(chain, "tip", ["https://a"], 2, "sys", "user")
    assert draft.variants == ("short one", "short two")
    assert draft.post_type == "tip" and draft.source_urls == ("https://a",)
    assert chain.calls[0][2] > 0.5


def test_generate_retries_once_when_over_length():
    too_long = "x" * 300
    chain = FakeChain([_raw([too_long, "ok"]), _raw(["fine", "also fine"])])
    draft = generate(chain, "build", [], 2, "sys", "user")
    assert draft.variants == ("fine", "also fine")
    assert len(chain.calls) == 2
    assert too_long in chain.calls[1][1] and "300" in chain.calls[1][1]


def test_generate_raises_when_still_over_length():
    too_long = "x" * 300
    chain = FakeChain([_raw([too_long, "ok"]), _raw([too_long, "ok"])])
    with pytest.raises(DraftError):
        generate(chain, "build", [], 2, "sys", "user")


def test_generate_lets_provider_failure_propagate():
    class Failing:
        def complete(self, *a, **k):
            raise AllProvidersFailed("none")

    with pytest.raises(AllProvidersFailed):
        generate(Failing(), "build", [], 2, "sys", "user")


def test_build_messages_includes_recent_whys_and_brief():
    system, user = build_messages(
        "question", "material text", "PERSONA", "VOICE", "CONTEXT", "KNOWLEDGE",
        "- 2026-11-12 · Src · headline", ["asked about latency"], 2,
    )
    for part in ("PERSONA", "VOICE", "CONTEXT", "KNOWLEDGE", "asked about latency", "280"):
        assert part in system
    assert "material text" in user and "headline" in user


def test_build_messages_has_instruction_for_every_type():
    assert set(TYPE_BRIEFS) == set(POST_TYPES)
    for post_type in POST_TYPES:
        _, user = build_messages(post_type, "m", "p", "v", "c", "k", "", [], 2)
        assert TYPE_BRIEFS[post_type] in user

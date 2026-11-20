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


@pytest.mark.parametrize("bad", ["Read it here <link>", "See <URL> now", "Check [link]", "by <your name>"])
def test_parse_draft_rejects_placeholder_text(bad):
    with pytest.raises(DraftError):
        parse_draft(_raw([bad, "fine"]), 2)


def test_parse_draft_allows_normal_angle_brackets():
    variants, _ = parse_draft(_raw(["I <3 voice agents", "a < b and c > d"]), 2)
    assert len(variants) == 2


def test_build_messages_tells_model_which_link_to_use():
    system, user = build_messages("agora_news", "m", "p", "v", "c", "k", "", [], 2, links=["https://agora.io/post"])
    assert "https://agora.io/post" in user
    assert "never write placeholders" in system.lower()


def test_build_messages_says_no_link_when_none_given():
    _, user = build_messages("tip", "m", "p", "v", "c", "k", "", [], 2)
    assert "no link" in user.lower()


def test_system_prompt_limits_claims_to_what_the_material_says():
    system, _ = build_messages("agora_news", "m", "p", "v", "c", "k", "", [], 2)
    assert "if the material is only a title" in system.lower()


def test_tweet_length_counts_bare_domains_as_links():
    assert tweet_length("see agora.io") == 4 + 23
    assert tweet_length("a docs.agora.io/en/rtc?x=1") == 2 + 23


def test_tweet_length_does_not_treat_code_names_as_domains():
    assert tweet_length("Next.js and index.html") == len("Next.js and index.html")


@pytest.mark.parametrize("code", ["Wrap your app in <AgoraRTCProvider> first", "Use a <video> element", "<Button> works"])
def test_parse_draft_allows_code_tags(code):
    variants, _ = parse_draft(_raw([code, "fine"]), 2)
    assert variants[0] == code


def _gen(variants, allowed):
    chain = FakeChain([_raw(variants)])
    return generate(chain, "agora_news", allowed, 2, "sys", "user")


def test_generate_rejects_a_link_the_model_was_not_given():
    with pytest.raises(DraftError):
        _gen(["Read https://www.agora.io/en/success-stories/lola/ now", "ok"], ["https://docs.agora.io/real"])


def test_generate_accepts_the_given_link_even_with_trailing_punctuation_and_www():
    draft = _gen(["See https://www.docs.agora.io/real.", "Also https://docs.agora.io/real/?utm_source=x"], ["https://docs.agora.io/real"])
    assert len(draft.variants) == 2


def test_generate_rejects_any_link_when_none_were_given():
    with pytest.raises(DraftError):
        _gen(["Try https://example.com/x", "ok"], [])


def test_generate_rejects_an_invented_bare_domain_path_but_allows_a_bare_domain():
    with pytest.raises(DraftError):
        _gen(["see agora.io/en/made-up", "ok"], [])
    assert len(_gen(["we use agora.io daily", "ok"], []).variants) == 2

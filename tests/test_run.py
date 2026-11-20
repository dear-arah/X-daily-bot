from datetime import datetime, timezone

from tests.helpers import FakeChain, Poster, Resp, make_settings, rss
from xpost.llm.providers import AllProvidersFailed
from xpost.models import Source
from xpost.run import run_daily
from xpost.state import State, normalize_url
from xpost.verify import PageCheck

NOW = datetime(2026, 11, 13, 0, 27, tzinfo=timezone.utc)
HOOK = "https://discord.test/hook"


def _ok(url):
    return PageCheck("ok", url, "")


def _go(tmp_path, settings, chain=None, poster=None, sources=(), feeds=None, now=NOW, check=_ok, **kwargs):
    feeds = feeds or {}
    state = State(tmp_path / "state.json")

    def get(url, **kw):
        return Resp(feeds[url]) if url in feeds else Resp(status=404)

    chain = chain or FakeChain()
    poster = poster or Poster()
    result = run_daily(
        settings, list(sources), state, chain, now, HOOK, get=get, post=poster, files_root=tmp_path, check=check, **kwargs
    )
    return result, state, chain, poster


def test_skips_when_already_drafted_today(tmp_path):
    settings = make_settings(tmp_path)
    _go(tmp_path, settings)
    result, _, chain, poster = _go(tmp_path, settings)
    assert result.status == "skipped" and chain.calls == [] and poster.bodies == []


def test_force_runs_again(tmp_path):
    settings = make_settings(tmp_path)
    _go(tmp_path, settings)
    result, *_ = _go(tmp_path, settings, force=True)
    assert result.status == "posted"


def test_first_run_picks_agora_news_from_linkedin_inbox_entry(tmp_path):
    settings = make_settings(tmp_path, inbox="[linkedin]\nAgora launched Agent Studio https://agora.io/p\n")
    result, state, chain, poster = _go(tmp_path, settings)
    assert result.status == "posted" and result.post_type == "agora_news"
    system, user = chain.calls[0]
    assert "Agora launched Agent Studio" in user
    assert "PERSONA TEXT" in system and "VOICE TEXT" in system and "CONTEXT TEXT" in system
    assert "https://agora.io/p" in poster.bodies[0]["embeds"][0]["description"]
    assert State(tmp_path / "state.json").last_type() == "agora_news"


def test_agora_news_falls_back_to_agora_feed_item(tmp_path):
    settings = make_settings(tmp_path)
    sources = [Source("Agora blog", "https://feed/agora", "agora")]
    feeds = {"https://feed/agora": rss(("Agora ships thing", "https://agora.io/thing"))}
    result, state, chain, _ = _go(tmp_path, settings, sources=sources, feeds=feeds)
    assert result.post_type == "agora_news" and "Agora ships thing" in chain.calls[0][1]
    assert "Source: Agora blog" in chain.calls[0][1]
    assert "https://agora.io/thing" in chain.calls[0][1]
    assert State(tmp_path / "state.json").is_seen("https://agora.io/thing")


def test_falls_back_to_next_type_when_source_missing(tmp_path):
    settings = make_settings(tmp_path, inbox="[note]\nI tried a voice agent this week\n")
    result, *_ = _go(tmp_path, settings)
    assert result.post_type == "build"


def test_question_type_works_with_no_sources(tmp_path):
    result, _, chain, poster = _go(tmp_path, make_settings(tmp_path))
    assert result.status == "posted" and result.post_type == "question"
    assert len(poster.bodies) == 1


def test_event_type_needs_inbox_entry(tmp_path):
    settings = make_settings(tmp_path, inbox="[event]\nWebinar on voice agents https://agora.io/w\n")
    state = State(tmp_path / "state.json")
    from xpost.models import Draft
    from datetime import date

    state.record(Draft("question", ("a", "b"), "w", ()), [], date(2026, 11, 12))
    state.save()
    result, *_ = _go(tmp_path, settings)
    assert result.post_type == "event"


def test_tip_uses_unused_knowledge_topic_and_marks_it(tmp_path):
    settings = make_settings(tmp_path, with_knowledge=True)
    state = State(tmp_path / "state.json")
    from xpost.models import Draft
    from datetime import date

    state.record(Draft("build", ("a", "b"), "w", ()), [], date(2026, 11, 12))
    state.save()
    result, _, chain, _ = _go(tmp_path, settings)
    assert result.post_type == "tip"
    assert "Use the web SDK" in chain.calls[0][1]
    assert State(tmp_path / "state.json").is_seen("topic:rtc/web.md")


def test_posted_run_records_state_and_consumes_inbox_entry(tmp_path):
    settings = make_settings(tmp_path, inbox="[linkedin]\nBig news today\n")
    _go(tmp_path, settings)
    reloaded = State(tmp_path / "state.json")
    from xpost.inbox import parse_inbox

    assert reloaded.is_seen(parse_inbox("[linkedin]\nBig news today")[0].id)


def test_second_run_next_day_does_not_reuse_consumed_entry(tmp_path):
    settings = make_settings(tmp_path, inbox="[linkedin]\nBig news today\n")
    _go(tmp_path, settings)
    next_day = datetime(2026, 11, 14, 0, 27, tzinfo=timezone.utc)
    result, _, chain, _ = _go(tmp_path, settings, now=next_day)
    assert result.status == "posted" and result.post_type != "agora_news"
    assert "Big news today" not in chain.calls[0][1]


def test_discord_failure_returns_failed_and_leaves_state_untouched(tmp_path):
    settings = make_settings(tmp_path, inbox="[linkedin]\nBig news today\n")
    result, *_ = _go(tmp_path, settings, poster=Poster(status=500))
    assert result.status == "failed"
    assert not (tmp_path / "state.json").exists()


def test_all_providers_failed_sends_notice_and_returns_no_draft(tmp_path):
    chain = FakeChain(error=AllProvidersFailed("none"))
    result, _, _, poster = _go(tmp_path, make_settings(tmp_path), chain=chain)
    assert result.status == "no_draft"
    assert poster.bodies[0]["content"].startswith("No draft today")
    assert not (tmp_path / "state.json").exists()


def test_over_length_model_output_sends_notice(tmp_path):
    chain = FakeChain(variants=("x" * 400, "y" * 400))
    result, _, _, poster = _go(tmp_path, make_settings(tmp_path), chain=chain)
    assert result.status == "no_draft" and "No draft today" in poster.bodies[0]["content"]


def test_dry_run_does_not_post_or_save_state(tmp_path):
    result, _, _, poster = _go(tmp_path, make_settings(tmp_path), dry_run=True)
    assert result.status == "dry_run" and poster.bodies == []
    assert "Variant one text" in result.message and "https://x.com/intent/tweet?text=" in result.message
    assert not (tmp_path / "state.json").exists()


def test_missing_knowledge_dir_still_drafts(tmp_path):
    result, *_ = _go(tmp_path, make_settings(tmp_path))
    assert result.status == "posted"


def test_empty_and_malformed_inbox_is_fine(tmp_path):
    for text in ("", "\n\n", "---\n---\n[event]\n", "# only a comment"):
        sub = tmp_path / str(abs(hash(text)))
        sub.mkdir()
        result, *_ = _go(sub, make_settings(sub, inbox=text))
        assert result.status == "posted", text


def test_google_news_link_is_resolved_before_it_reaches_the_prompt_and_draft(tmp_path):
    google = "https://news.google.com/rss/articles/CBMiabc?oc=5"
    sources = [Source("agora.io (news search)", "https://feed/agora", "agora")]
    feeds = {"https://feed/agora": rss(("Agora docs guide", google))}
    settings = make_settings(tmp_path)
    state = State(tmp_path / "state.json")
    chain, poster = FakeChain(), Poster()

    def get(url, **kw):
        return Resp(feeds[url]) if url in feeds else Resp(status=404)

    result = run_daily(
        settings, sources, state, chain, NOW, HOOK, get=get, post=poster, files_root=tmp_path,
        resolve=lambda url: "https://docs.agora.io/real-page", check=_ok,
    )
    assert result.status == "posted"
    user = chain.calls[0][1]
    assert "https://docs.agora.io/real-page" in user and "news.google.com" not in user
    assert "https://docs.agora.io/real-page" in poster.bodies[0]["embeds"][0]["description"]
    # the original link is what gets remembered, so the same item is never drafted twice
    assert State(tmp_path / "state.json").is_seen(normalize_url(google))


def test_event_entry_jumps_the_queue_so_the_reminder_is_not_late(tmp_path):
    settings = make_settings(tmp_path, inbox="[event]\nWebinar on voice agents https://agora.io/w\n")
    state = State(tmp_path / "state.json")
    from xpost.models import Draft
    from datetime import date

    state.record(Draft("tip", ("a", "b"), "w", ()), [], date(2026, 11, 12))  # rotation would say: question next
    state.save()
    result, *_ = _go(tmp_path, settings)
    assert result.post_type == "event"


def test_event_does_not_repeat_back_to_back(tmp_path):
    settings = make_settings(tmp_path, inbox="[event]\nSecond webinar https://agora.io/w2\n")
    state = State(tmp_path / "state.json")
    from xpost.models import Draft
    from datetime import date

    state.record(Draft("event", ("a", "b"), "w", ()), ["old"], date(2026, 11, 12))
    state.save()
    result, *_ = _go(tmp_path, settings)
    assert result.post_type != "event"


AGORA = [Source("Agora blog", "https://feed/agora", "agora")]


def _two_items():
    return {"https://feed/agora": rss(("Dead story", "https://agora.io/dead"), ("Live story", "https://agora.io/live"))}


def _dead_first(url):
    return PageCheck("dead", url, "") if url.endswith("/dead") else PageCheck("ok", url, "")


def test_dead_link_candidate_is_skipped_for_the_next_live_one(tmp_path):
    result, state, chain, _ = _go(tmp_path, make_settings(tmp_path), sources=AGORA, feeds=_two_items(), check=_dead_first)
    assert result.post_type == "agora_news"
    user = chain.calls[0][1]
    assert "Live story" in user and "Dead story" not in user and "agora.io/dead" not in user
    assert not State(tmp_path / "state.json").is_seen(normalize_url("https://agora.io/dead"))
    assert State(tmp_path / "state.json").is_seen(normalize_url("https://agora.io/live"))


def test_type_with_only_dead_links_falls_back_to_another_type(tmp_path):
    feeds = {"https://feed/agora": rss(("Dead story", "https://agora.io/dead"))}
    result, *_ = _go(tmp_path, make_settings(tmp_path), sources=AGORA, feeds=feeds, check=_dead_first)
    assert result.status == "posted" and result.post_type != "agora_news"


def test_real_page_text_is_given_to_the_model(tmp_path):
    check = lambda url: PageCheck("ok", url, "The page says latency stayed under 300 ms.")  # noqa: E731
    _, _, chain, _ = _go(tmp_path, make_settings(tmp_path), sources=AGORA, feeds=_two_items(), check=check)
    assert "The page says latency stayed under 300 ms." in chain.calls[0][1]


def test_unreachable_check_keeps_the_link_without_page_text(tmp_path):
    check = lambda url: PageCheck("unknown", url, "")  # noqa: E731
    result, _, chain, _ = _go(tmp_path, make_settings(tmp_path), sources=AGORA, feeds=_two_items(), check=check)
    assert result.post_type == "agora_news" and "Dead story" in chain.calls[0][1]


def test_link_invented_by_the_model_is_never_sent(tmp_path):
    chain = FakeChain(variants=("Saw it https://www.agora.io/en/success-stories/lola/", "second variant"))
    result, _, _, poster = _go(tmp_path, make_settings(tmp_path), chain=chain, sources=AGORA, feeds=_two_items())
    assert result.status == "no_draft"
    assert all("success-stories/lola" not in str(body) for body in poster.bodies)
    assert not (tmp_path / "state.json").exists()


def test_inbox_entry_with_a_dead_link_is_skipped_and_not_consumed(tmp_path):
    settings = make_settings(tmp_path, inbox="[linkedin]\nBig launch https://agora.io/dead\n")
    result, state, chain, _ = _go(tmp_path, settings, check=_dead_first)
    assert result.post_type != "agora_news" and "Big launch" not in chain.calls[0][1]
    from xpost.inbox import parse_inbox

    entry = parse_inbox("[linkedin]\nBig launch https://agora.io/dead")[0]
    assert not State(tmp_path / "state.json").is_seen(entry.id)

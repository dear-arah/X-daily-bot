import re
from datetime import date
from urllib.parse import unquote

from xpost.models import Draft
from xpost.post import build_message, build_notice, send

TODAY = date(2026, 11, 13)
LINK = re.compile(r"\[Post to X\]\((https://x\.com/intent/tweet\?text=[^)]+)\)")


def _draft(variants=("First variant", "Second variant\nwith a break"), sources=("https://a.com/x",)):
    return Draft("tip", tuple(variants), "it invites replies", tuple(sources))


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload


class ScriptedPost:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_build_message_has_link_per_variant():
    embed = build_message(_draft(), TODAY)["embeds"][0]
    links = LINK.findall(embed["description"])
    assert len(links) == 2
    assert unquote(links[0].split("text=")[1]) == "First variant"
    assert unquote(links[1].split("text=")[1]) == "Second variant\nwith a break"


def test_build_message_shows_title_why_and_sources():
    embed = build_message(_draft(), TODAY)["embeds"][0]
    assert embed["title"] == "Draft: Dev tip · 2026-11-13"
    assert "it invites replies" in embed["description"]
    assert "https://a.com/x" in embed["description"]
    assert "press Post on X" in embed["footer"]["text"]


def test_build_message_says_none_when_no_sources():
    embed = build_message(_draft(sources=()), TODAY)["embeds"][0]
    assert "Sources:** none" in embed["description"]


def test_build_message_shows_length_per_variant():
    embed = build_message(_draft(variants=("abc", "de")), TODAY)["embeds"][0]
    assert "(3/280)" in embed["description"] and "(2/280)" in embed["description"]


def test_build_message_stays_under_embed_limit_for_worst_case_emoji():
    heavy = "😀" * 140  # 280 weighted characters, 12 encoded characters each in the link
    embed = build_message(_draft(variants=(heavy, heavy), sources=("https://a.com/" + "p" * 900,)), TODAY)["embeds"][0]
    assert len(embed["description"]) <= 4096
    assert len(LINK.findall(embed["description"])) == 2


def test_build_notice_is_plain_content():
    assert build_notice("No draft today: x") == {"content": "No draft today: x"}


def test_send_returns_true_on_204():
    post = ScriptedPost(FakeResponse(204))
    assert send("https://hook", {"content": "hi"}, post=post, sleep=lambda s: None) is True
    assert post.calls[0][1]["json"] == {"content": "hi"}


def test_send_retries_once_on_429():
    post = ScriptedPost(FakeResponse(429, {"retry_after": 2}), FakeResponse(204))
    sleeps = []
    assert send("https://hook", {"content": "hi"}, post=post, sleep=sleeps.append) is True
    assert sleeps == [2.0] and len(post.calls) == 2


def test_send_returns_false_when_retry_also_rate_limited():
    post = ScriptedPost(FakeResponse(429), FakeResponse(429))
    assert send("https://hook", {}, post=post, sleep=lambda s: None) is False


def test_send_returns_false_on_failure():
    assert send("https://hook", {}, post=ScriptedPost(FakeResponse(500)), sleep=lambda s: None) is False
    assert send("https://hook", {}, post=ScriptedPost(TimeoutError("slow")), sleep=lambda s: None) is False

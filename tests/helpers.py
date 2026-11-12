"""Shared builders for run and CLI tests."""
from __future__ import annotations

import json
from pathlib import Path

from xpost.models import Settings


class Resp:
    def __init__(self, content=b"", status=200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {}


def rss(*entries):
    items = "".join(
        f"<item><title>{t}</title><link>{u}</link><description>{t} body</description>"
        f"<pubDate>Thu, 12 Nov 2026 10:00:00 GMT</pubDate></item>"
        for t, u in entries
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{items}</channel></rss>'.encode()


class FakeChain:
    def __init__(self, variants=("Variant one text", "Variant two text"), why="a fresh angle", error=None):
        self.variants = variants
        self.why = why
        self.error = error
        self.calls = []
        self.providers = [object()]  # mirrors FallbackChain.providers

    def complete(self, system, user, parse=None, temperature=0.2):
        self.calls.append((system, user))
        if self.error:
            raise self.error
        raw = json.dumps({"variants": list(self.variants), "why": self.why})
        return parse(raw) if parse else raw


class Poster:
    def __init__(self, status=204):
        self.status = status
        self.bodies = []

    def __call__(self, url, **kwargs):
        self.bodies.append(kwargs.get("json"))
        return Resp(status=self.status)


def make_settings(root: Path, inbox: str = "", with_knowledge: bool = False) -> Settings:
    (root / "inbox").mkdir(exist_ok=True)
    (root / "config").mkdir(exist_ok=True)
    (root / "inbox" / "notes.md").write_text(inbox)
    (root / "config" / "persona.md").write_text("PERSONA TEXT")
    (root / "config" / "voice.md").write_text("VOICE TEXT")
    (root / "config" / "agora-context.md").write_text("CONTEXT TEXT")
    if with_knowledge:
        refs = root / "knowledge" / "pack" / "skills" / "agora" / "references" / "rtc"
        refs.mkdir(parents=True)
        (root / "knowledge" / "pack" / "skills" / "agora" / "SKILL.md").write_text("Agora overview for voice agents.")
        (refs / "web.md").write_text("# Web RTC voice agent\nUse the web SDK for a voice agent in the browser.\n")
    from xpost.models import ProviderSpec

    return Settings(
        webhook_env="DISCORD_WEBHOOK_URL",
        providers=(ProviderSpec("gemini", "m"),),
        rotation=("agora_news", "build", "tip", "question", "event"),
        variants=2,
        max_age_days=14,
        brief_size=10,
        knowledge_dir="knowledge/pack",
        knowledge_budget_chars=6000,
        inbox_file="inbox/notes.md",
        sources_file="config/sources.yaml",
        persona_file="config/persona.md",
        voice_file="config/voice.md",
        context_file="config/agora-context.md",
    )

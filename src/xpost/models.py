from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

POST_TYPES = ("agora_news", "build", "tip", "question", "event")
GROUPS = ("agora", "own", "world")


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    group: str


@dataclass(frozen=True)
class Item:
    title: str
    url: str
    text: str
    published: datetime | None
    source: str
    group: str


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    model: str


@dataclass(frozen=True)
class Draft:
    post_type: str
    variants: tuple[str, ...]
    why: str
    source_urls: tuple[str, ...]


@dataclass(frozen=True)
class Settings:
    webhook_env: str
    providers: tuple[ProviderSpec, ...]
    rotation: tuple[str, ...]
    variants: int
    max_age_days: int
    brief_size: int
    knowledge_dir: str
    knowledge_budget_chars: int
    inbox_file: str
    sources_file: str
    persona_file: str
    voice_file: str
    context_file: str

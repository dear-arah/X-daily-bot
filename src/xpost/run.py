from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Sequence

import requests

from xpost.brief import build_brief
from xpost.collect import collect_all
from xpost.draft import MAX_WEIGHT, DraftError, build_messages, generate, intent_url, tweet_length
from xpost.inbox import InboxEntry, parse_inbox
from xpost.knowledge import core_text, list_topics, load_topic_text, pick_relevant
from xpost.llm.chain import FallbackChain
from xpost.llm.providers import AllProvidersFailed
from xpost.models import Draft, Item, Settings, Source
from xpost.post import build_message, build_notice, send
from xpost.resolve import resolve_url
from xpost.rotation import pick_type
from xpost.state import State, normalize_url

log = logging.getLogger(__name__)

TIP_QUERY = "voice agent conversational real-time developers build"


@dataclass(frozen=True)
class RunResult:
    status: str  # posted | dry_run | skipped | no_draft | failed
    post_type: str | None
    message: str


@dataclass(frozen=True)
class _Candidate:
    material: str
    urls: tuple[str, ...]
    keys: tuple[str, ...]


def format_plain(draft: Draft, today) -> str:
    lines = [f"Draft ({draft.post_type}) for {today.isoformat()}"]
    for number, variant in enumerate(draft.variants, start=1):
        lines += ["", f"Variant {number} ({tweet_length(variant)}/{MAX_WEIGHT}):", variant, f"Post to X: {intent_url(variant)}"]
    lines += ["", f"Why: {draft.why}", f"Sources: {', '.join(draft.source_urls) or 'none'}"]
    return "\n".join(lines)


def _entry_candidate(entry: InboxEntry) -> _Candidate:
    return _Candidate(entry.text, entry.urls, (entry.id,))


def _item_candidate(item: Item) -> _Candidate:
    material = f"Source: {item.source}\n{item.title}\n{item.text}\nURL: {item.url}".strip()
    return _Candidate(material, (item.url,), (normalize_url(item.url),))


def _first(entries: Sequence[InboxEntry], *tags: str) -> InboxEntry | None:
    return next((e for e in entries if e.tag in tags), None)


def _candidates(
    settings: Settings,
    state: State,
    entries: Sequence[InboxEntry],
    items: Sequence[Item],
    brief: str,
    knowledge_root: Path,
) -> dict[str, _Candidate]:
    found: dict[str, _Candidate] = {}

    def newest(group: str) -> Item | None:
        return next((i for i in items if i.group == group), None)

    entry, item = _first(entries, "linkedin"), newest("agora")
    if entry or item:
        found["agora_news"] = _entry_candidate(entry) if entry else _item_candidate(item)

    entry, item = _first(entries, "built", "note"), newest("own")
    if entry or item:
        found["build"] = _entry_candidate(entry) if entry else _item_candidate(item)

    topics = {t.key: t for t in list_topics(knowledge_root)}
    exclude = {key for key in topics if state.is_seen(f"topic:{key}")}
    _, keys = pick_relevant(knowledge_root, f"{TIP_QUERY} {brief}", settings.knowledge_budget_chars, exclude)
    if keys:
        text = load_topic_text(topics[keys[0]], settings.knowledge_budget_chars)
        found["tip"] = _Candidate(text, (), (f"topic:{keys[0]}",))

    top_line = brief.splitlines()[0] if brief else ""
    found["question"] = _Candidate(top_line, (), ())

    entry = _first(entries, "event")
    if entry:
        found["event"] = _entry_candidate(entry)
    return found


def _with_resolved_links(candidate: _Candidate, resolve: Callable[[str], str]) -> _Candidate:
    """Swap news-search redirect links for the publisher's own URL; the remembered keys stay as they were."""
    material, urls = candidate.material, []
    for url in candidate.urls:
        real = resolve(url)
        material = material.replace(url, real)
        urls.append(real)
    return _Candidate(material, tuple(urls), candidate.keys)


def _notice(webhook_url: str | None, post: Callable, dry_run: bool, reason: str) -> str:
    text = f"No draft today: {reason}"
    if not dry_run and webhook_url:
        send(webhook_url, build_notice(text), post=post)
    return text


def run_daily(
    settings: Settings,
    sources: Sequence[Source],
    state: State,
    chain: FallbackChain,
    now: datetime,
    webhook_url: str | None,
    get: Callable = requests.get,
    post: Callable = requests.post,
    dry_run: bool = False,
    force: bool = False,
    files_root: Path = Path("."),
    resolve: Callable[[str], str] = resolve_url,
) -> RunResult:
    today = now.date()
    if state.drafted_today(today) and not force:
        return RunResult("skipped", None, "Already drafted today; use --force to draft again.")

    root = Path(files_root)
    inbox_path = root / settings.inbox_file
    inbox_text = inbox_path.read_text() if inbox_path.exists() else ""
    entries = [e for e in parse_inbox(inbox_text) if not state.is_seen(e.id)]

    cutoff = now - timedelta(days=settings.max_age_days)
    all_items = collect_all(sources, get=get)
    fresh = [
        i
        for i in all_items
        if not state.is_seen(normalize_url(i.url)) and (i.published is None or i.published >= cutoff)
    ]
    fresh.sort(key=lambda i: i.published.timestamp() if i.published else 0, reverse=True)
    brief = build_brief(all_items, now, settings.max_age_days, settings.brief_size)

    knowledge_root = root / settings.knowledge_dir
    candidates = _candidates(settings, state, entries, fresh, brief, knowledge_root)
    post_type = pick_type(state.last_type(), candidates.keys(), settings.rotation)
    if post_type is None:
        return RunResult("no_draft", None, _notice(webhook_url, post, dry_run, "no material for any post type"))
    chosen = _with_resolved_links(candidates[post_type], resolve)

    knowledge = "\n\n".join(
        part
        for part in (
            core_text(knowledge_root, settings.knowledge_budget_chars),
            pick_relevant(knowledge_root, chosen.material, settings.knowledge_budget_chars)[0],
        )
        if part
    )
    system, user = build_messages(
        post_type,
        chosen.material,
        (root / settings.persona_file).read_text(),
        (root / settings.voice_file).read_text(),
        (root / settings.context_file).read_text(),
        knowledge,
        brief,
        state.recent_whys(),
        settings.variants,
        links=chosen.urls,
    )
    try:
        draft = generate(chain, post_type, chosen.urls, settings.variants, system, user)
    except (DraftError, AllProvidersFailed) as exc:
        log.warning("drafting failed: %s", exc)
        return RunResult("no_draft", post_type, _notice(webhook_url, post, dry_run, f"the model could not write a usable draft ({exc})"))

    plain = format_plain(draft, today)
    if dry_run:
        return RunResult("dry_run", post_type, plain)

    if not send(webhook_url, build_message(draft, today), post=post):
        return RunResult("failed", post_type, "Discord rejected the post; nothing was saved.")

    state.record(draft, chosen.keys, today)
    state.prune(today)
    state.save()
    return RunResult("posted", post_type, plain)

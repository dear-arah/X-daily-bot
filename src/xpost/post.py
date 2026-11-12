from __future__ import annotations

import logging
import time
from datetime import date
from typing import Callable

import requests

from xpost.draft import MAX_WEIGHT, intent_url, tweet_length
from xpost.models import Draft

log = logging.getLogger(__name__)

DESCRIPTION_LIMIT = 4096
SOURCES_LIMIT = 600
MAX_RETRY_WAIT = 30.0
_COLOR = 0x1D9BF0
_TYPE_NAMES = {
    "agora_news": "Saw this from Agora",
    "build": "Build in public",
    "tip": "Dev tip",
    "question": "Community question",
    "event": "Event reminder",
}


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" for line in text.splitlines()) or "> "


def build_message(draft: Draft, today: date) -> dict:
    blocks = []
    for number, variant in enumerate(draft.variants, start=1):
        blocks.append(
            f"**Variant {number}** ({tweet_length(variant)}/{MAX_WEIGHT})\n"
            f"{_quote(variant)}\n"
            f"[Post to X]({intent_url(variant)})"
        )
    sources = ", ".join(draft.source_urls)[:SOURCES_LIMIT] or "none"
    blocks.append(f"**Why this angle:** {draft.why}")
    blocks.append(f"**Sources:** {sources}")
    embed = {
        "title": f"Draft: {_TYPE_NAMES.get(draft.post_type, draft.post_type)} · {today.isoformat()}",
        "description": "\n\n".join(blocks)[:DESCRIPTION_LIMIT],
        "color": _COLOR,
        "footer": {"text": "Review, edit if you like, then press Post on X."},
    }
    return {"embeds": [embed]}


def build_notice(text: str) -> dict:
    return {"content": text}


def send(
    webhook_url: str,
    body: dict,
    post: Callable = requests.post,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    for attempt in range(2):
        try:
            response = post(webhook_url, json=body, timeout=15)
        except Exception as exc:
            log.warning("discord post failed: %s", exc)
            return False

        if 200 <= response.status_code < 300:
            return True
        if response.status_code == 429 and attempt == 0:
            try:
                wait = float(response.json().get("retry_after", 1))
            except Exception:  # an HTML 429 from a proxy has no JSON body
                wait = 1.0
            sleep(min(wait, MAX_RETRY_WAIT))
            continue
        log.warning("discord returned HTTP %s", response.status_code)
        return False
    return False

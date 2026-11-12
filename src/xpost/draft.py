from __future__ import annotations

import json
import re
from typing import Sequence
from urllib.parse import quote

from xpost.llm.chain import FallbackChain
from xpost.models import Draft

MAX_WEIGHT = 280
URL_WEIGHT = 23
CREATIVE_TEMPERATURE = 0.8

_URL = re.compile(r"https?://\S+")
_SINGLE_WEIGHT = ((0x0000, 0x10FF), (0x2000, 0x200D), (0x2010, 0x201F), (0x2032, 0x2037))

TYPE_BRIEFS = {
    "agora_news": (
        "Post type: Saw this from Agora. Share something Agora announced or published, as a developer who noticed it. "
        "Say why it matters to people building with it. Do not repeat the source's wording."
    ),
    "build": (
        "Post type: Build in public. Turn the material (the user's own build, article or note) into a first-person "
        "post about what they made or learned. Open with a hook, keep it concrete, end with one link if there is one."
    ),
    "tip": (
        "Post type: Dev tip. Give one small, concrete, accurate tip from the Agora knowledge provided, "
        "something a developer can use today. Use only facts that appear in that knowledge."
    ),
    "question": (
        "Post type: Community question. Ask developers one specific, easy-to-answer question connected to the "
        "tech news below or to building voice and real-time apps. Invite replies; no link needed."
    ),
    "event": (
        "Post type: Event reminder. Tell developers about the event in the material, what they will get out of it, "
        "and include its link. Keep dates and names exactly as given."
    ),
}

_SYSTEM = """{persona}

{voice}

Rules:
- Use only facts present in the material and the Agora knowledge below. Never invent product capabilities, dates or numbers.
- Write as the user, in first person. Never copy the source's wording: add an opinion, a reason a developer should care, or a question.
- At most one hashtag, and only if it helps. No emoji walls.
- Each variant must be at most {limit} characters (a link counts as 23). The two variants must take different angles.
- Avoid repeating these recent angles:
{recent}
- Reply with a single JSON object and nothing else: {{"variants": [{count} strings], "why": "one sentence on why this angle should start replies"}}

Agora context:
{context}

Agora knowledge:
{knowledge}"""


class DraftError(ValueError):
    pass


def tweet_length(text: str) -> int:
    urls = _URL.findall(text)
    rest = _URL.sub("", text)
    weight = sum(1 if any(lo <= ord(c) <= hi for lo, hi in _SINGLE_WEIGHT) else 2 for c in rest)
    return weight + URL_WEIGHT * len(urls)


def intent_url(text: str) -> str:
    return "https://x.com/intent/tweet?text=" + quote(text, safe="")


def build_messages(
    post_type: str,
    material: str,
    persona: str,
    voice: str,
    context: str,
    knowledge: str,
    brief: str,
    recent_whys: Sequence[str],
    variants: int,
) -> tuple[str, str]:
    recent = "\n".join(f"  - {w}" for w in recent_whys) or "  (none yet)"
    system = _SYSTEM.format(
        persona=persona.strip(),
        voice=voice.strip(),
        limit=MAX_WEIGHT,
        recent=recent,
        count=variants,
        context=context.strip(),
        knowledge=knowledge.strip() or "(not available today)",
    )
    user = (
        f"{TYPE_BRIEFS[post_type]}\n\n"
        f"Material:\n{material.strip() or '(none; use the news below)'}\n\n"
        f"What is happening in tech this week:\n{brief.strip() or '(nothing notable)'}"
    )
    return system, user


def parse_draft(raw: str, variants: int) -> tuple[tuple[str, ...], str]:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise DraftError("no JSON object in model output")
    try:
        data = json.loads(raw[start : end + 1])
    except ValueError as exc:
        raise DraftError(f"invalid JSON: {exc}") from exc
    texts = data.get("variants") if isinstance(data, dict) else None
    why = data.get("why") if isinstance(data, dict) else None
    if (
        not isinstance(texts, list)
        or len(texts) != variants
        or not all(isinstance(t, str) and t.strip() for t in texts)
    ):
        raise DraftError(f"expected {variants} non-empty variants")
    if not isinstance(why, str) or not why.strip():
        raise DraftError("missing 'why'")
    return tuple(t.strip() for t in texts), why.strip()


def _too_long(variants: Sequence[str]) -> list[tuple[str, int]]:
    return [(v, tweet_length(v)) for v in variants if tweet_length(v) > MAX_WEIGHT]


def generate(
    chain: FallbackChain,
    post_type: str,
    source_urls: Sequence[str],
    variants: int,
    system: str,
    user: str,
) -> Draft:
    parse = lambda raw: parse_draft(raw, variants)  # noqa: E731
    texts, why = chain.complete(system, user, parse=parse, temperature=CREATIVE_TEMPERATURE)
    over = _too_long(texts)
    if over:
        complaint = "\n".join(f'- "{v}" is {n} characters' for v, n in over)
        retry_user = f"{user}\n\nYour previous reply was too long (limit {MAX_WEIGHT}):\n{complaint}\nWrite shorter variants."
        texts, why = chain.complete(system, retry_user, parse=parse, temperature=CREATIVE_TEMPERATURE)
        if _too_long(texts):
            raise DraftError("model kept returning variants over the length limit")
    return Draft(post_type=post_type, variants=texts, why=why, source_urls=tuple(source_urls))

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from xpost.models import GROUPS, POST_TYPES, ProviderSpec, Settings, Source


class ConfigError(ValueError):
    pass


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a mapping at the top level")
    return data


def _require(data: dict[str, Any], key: str, where: str) -> Any:
    if key not in data:
        raise ConfigError(f"{where}: missing '{key}'")
    return data[key]


def load_settings(path: Path) -> Settings:
    data = _read_yaml(path)
    where = str(path)

    providers = tuple(
        ProviderSpec(name=_require(p, "name", where), model=_require(p, "model", where))
        for p in _require(data, "providers", where) or ()
    )
    if not providers:
        raise ConfigError(f"{where}: providers must not be empty")

    rotation = tuple(_require(data, "rotation", where))
    unknown = [t for t in rotation if t not in POST_TYPES]
    if unknown or not rotation:
        raise ConfigError(f"{where}: rotation must use only {', '.join(POST_TYPES)} (got {unknown or 'nothing'})")

    return Settings(
        webhook_env=_require(data, "webhook_env", where),
        providers=providers,
        rotation=rotation,
        variants=int(_require(data, "variants", where)),
        max_age_days=int(_require(data, "max_age_days", where)),
        brief_size=int(_require(data, "brief_size", where)),
        knowledge_dir=_require(data, "knowledge_dir", where),
        knowledge_budget_chars=int(_require(data, "knowledge_budget_chars", where)),
        inbox_file=_require(data, "inbox_file", where),
        sources_file=_require(data, "sources_file", where),
        persona_file=_require(data, "persona_file", where),
        voice_file=_require(data, "voice_file", where),
        context_file=_require(data, "context_file", where),
    )


def load_sources(path: Path) -> tuple[Source, ...]:
    data = _read_yaml(path)
    where = str(path)
    sources = []
    for entry in _require(data, "sources", where) or ():
        group = _require(entry, "group", where)
        if group not in GROUPS:
            raise ConfigError(f"{where}: group must be one of {', '.join(GROUPS)}, got {group!r}")
        sources.append(
            Source(
                name=_require(entry, "name", where),
                url=_require(entry, "url", where),
                group=group,
                must_match=tuple(str(p) for p in entry.get("must_match") or ()),
            )
        )
    return tuple(sources)

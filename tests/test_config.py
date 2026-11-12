import pytest

from xpost.config import ConfigError, load_settings, load_sources
from xpost.models import POST_TYPES

BOT_YAML = """
webhook_env: DISCORD_WEBHOOK_URL
providers:
  - {name: gemini, model: m1}
  - {name: groq, model: m2}
rotation: [agora_news, build, tip, question, event]
variants: 2
max_age_days: 14
brief_size: 10
knowledge_dir: knowledge/agora-skills
knowledge_budget_chars: 6000
inbox_file: inbox/notes.md
sources_file: config/sources.yaml
persona_file: config/persona.md
voice_file: config/voice.md
context_file: config/agora-context.md
"""


def _write(tmp_path, text, name="bot.yaml"):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_load_settings_reads_all_fields(tmp_path):
    settings = load_settings(_write(tmp_path, BOT_YAML))
    assert settings.rotation == POST_TYPES
    assert settings.variants == 2
    assert [p.name for p in settings.providers] == ["gemini", "groq"]
    assert settings.providers[1].model == "m2"
    assert settings.inbox_file == "inbox/notes.md"
    assert settings.knowledge_budget_chars == 6000


def test_load_settings_rejects_unknown_rotation_type(tmp_path):
    bad = BOT_YAML.replace("event]", "event, poll]")
    with pytest.raises(ConfigError):
        load_settings(_write(tmp_path, bad))


def test_load_settings_rejects_empty_providers(tmp_path):
    bad = BOT_YAML.replace("  - {name: gemini, model: m1}\n  - {name: groq, model: m2}\n", "")
    bad = bad.replace("providers:\n", "providers: []\n")
    with pytest.raises(ConfigError):
        load_settings(_write(tmp_path, bad))


def test_load_sources_requires_known_group(tmp_path):
    path = _write(tmp_path, "sources:\n  - {name: A, url: 'http://a', group: x}\n", "s.yaml")
    with pytest.raises(ConfigError):
        load_sources(path)


def test_load_sources_returns_sources_in_file_order(tmp_path):
    path = _write(
        tmp_path,
        "sources:\n  - {name: A, url: 'http://a', group: agora}\n  - {name: B, url: 'http://b', group: world}\n",
        "s.yaml",
    )
    sources = load_sources(path)
    assert [(s.name, s.group) for s in sources] == [("A", "agora"), ("B", "world")]

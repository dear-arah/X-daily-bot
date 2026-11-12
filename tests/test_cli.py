from pathlib import Path

import yaml

from tests.helpers import FakeChain, make_settings
from xpost import __main__ as cli


def _project(tmp_path: Path):
    make_settings(tmp_path)
    (tmp_path / "config" / "sources.yaml").write_text("sources: []\n")
    (tmp_path / "config" / "bot.yaml").write_text(
        yaml.safe_dump(
            {
                "webhook_env": "DISCORD_WEBHOOK_URL",
                "providers": [{"name": "gemini", "model": "m"}],
                "rotation": ["agora_news", "build", "tip", "question", "event"],
                "variants": 2,
                "max_age_days": 14,
                "brief_size": 10,
                "knowledge_dir": "knowledge/pack",
                "knowledge_budget_chars": 6000,
                "inbox_file": "inbox/notes.md",
                "sources_file": "config/sources.yaml",
                "persona_file": "config/persona.md",
                "voice_file": "config/voice.md",
                "context_file": "config/agora-context.md",
            }
        )
    )


def test_dry_run_prints_message_without_webhook(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(cli, "build_chain", lambda specs, env: FakeChain())
    code = cli.main(["run", "--dry-run", "--config", "config/bot.yaml"])
    assert code == 0
    assert "Variant one text" in capsys.readouterr().out


def test_missing_webhook_exits_2(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    code = cli.main(["run", "--config", "config/bot.yaml"])
    assert code == 2
    assert "DISCORD_WEBHOOK_URL" in capsys.readouterr().err

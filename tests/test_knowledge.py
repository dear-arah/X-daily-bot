from pathlib import Path

from xpost.knowledge import core_text, list_topics, pick_relevant


def _tree(tmp_path: Path) -> Path:
    base = tmp_path / "pack" / "skills" / "agora"
    refs = base / "references"
    (refs / "conversational-ai").mkdir(parents=True)
    (refs / "rtc").mkdir()
    (refs / "testing-guidance").mkdir()
    (base / "SKILL.md").write_text("S" * 3000)
    (refs / "conversational-ai" / "quickstarts.md").write_text("# Voice agent quickstart\n\nBuild it fast.\n")
    (refs / "rtc" / "web.md").write_text("no heading here. voice voice voice\n")
    (refs / "testing-guidance" / "rtc-web.md").write_text("# Testing\nvoice agent quickstart\n")
    (refs / "doc-fetching.md").write_text("# Fetching docs\nvoice agent quickstart\n")
    return tmp_path / "pack"


def test_list_topics_skips_testing_guidance(tmp_path):
    keys = [t.key for t in list_topics(_tree(tmp_path))]
    assert keys == ["conversational-ai/quickstarts.md", "rtc/web.md"]


def test_topic_title_from_first_heading_with_stem_fallback(tmp_path):
    titles = {t.key: t.title for t in list_topics(_tree(tmp_path))}
    assert titles["conversational-ai/quickstarts.md"] == "Voice agent quickstart"
    assert titles["rtc/web.md"] == "web"


def test_pick_relevant_ranks_title_hits_first(tmp_path):
    text, keys = pick_relevant(_tree(tmp_path), "voice agent quickstart", budget_chars=5000)
    assert keys[0] == "conversational-ai/quickstarts.md"
    assert "Build it fast." in text


def test_pick_relevant_respects_budget_and_exclude(tmp_path):
    root = _tree(tmp_path)
    text, keys = pick_relevant(root, "voice", budget_chars=40)
    assert len(text) <= 40
    _, keys = pick_relevant(root, "voice", 5000, exclude={"rtc/web.md"})
    assert "rtc/web.md" not in keys


def test_pick_relevant_skips_zero_score_topics(tmp_path):
    _, keys = pick_relevant(_tree(tmp_path), "kubernetes", budget_chars=5000)
    assert keys == []


def test_missing_root_returns_empty(tmp_path):
    missing = tmp_path / "nope"
    assert list_topics(missing) == []
    assert core_text(missing, 900) == ""
    assert pick_relevant(missing, "voice", 900) == ("", [])


def test_core_text_truncates(tmp_path):
    assert len(core_text(_tree(tmp_path), 300)) == 100

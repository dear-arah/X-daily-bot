from xpost.inbox import TAG_TO_TYPE, parse_inbox


def test_parses_tagged_entries_split_by_dashes():
    text = "[linkedin]\nBig launch today\n---\n[event]\nWebinar Friday\n---\njust a thought"
    entries = parse_inbox(text)
    assert [e.tag for e in entries] == ["linkedin", "event", "note"]
    assert entries[0].text == "Big launch today"
    assert entries[2].text == "just a thought"


def test_extracts_urls():
    entries = parse_inbox("[event]\nJoin us https://a.com/x), see you")
    assert entries[0].urls == ("https://a.com/x",)


def test_drops_empty_and_comment_only_input():
    assert parse_inbox("") == []
    assert parse_inbox("   \n") == []
    assert parse_inbox("# header only") == []
    assert parse_inbox("[event]\n---\n[note]") == []


def test_unknown_tag_becomes_note():
    entries = parse_inbox("[weird]\nsome text")
    assert entries[0].tag == "note"
    assert entries[0].text == "some text"


def test_id_is_stable_across_whitespace_changes():
    a = parse_inbox("[note]\nI  tried   voice agents")[0]
    b = parse_inbox("[note]\nI tried voice agents\n")[0]
    assert a.id == b.id and len(a.id) == 12


def test_comment_header_before_first_separator_is_dropped():
    entries = parse_inbox("# how to use\n# more help\n---\n[note]\nreal entry")
    assert [e.text for e in entries] == ["real entry"]


def test_tag_map_covers_all_tags():
    assert TAG_TO_TYPE == {"linkedin": "agora_news", "event": "event", "built": "build", "note": "build"}

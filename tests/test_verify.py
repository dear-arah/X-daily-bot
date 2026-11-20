from xpost.verify import check_url, page_text

HTML = """<html><head><title>LOLA Success Story</title>
<meta name="description" content="How LOLA built live voice rooms.">
<style>.x{color:red}</style><script>var secret = 1;</script></head>
<body><nav>Menu Home</nav><h1>Customer story</h1><p>LOLA moved to real-time voice.</p>
<p>Latency stayed under 300 ms.</p><footer>Copyright</footer></body></html>"""


class Page:
    def __init__(self, status=200, text=HTML, url="https://example.com/final", ctype="text/html; charset=utf-8"):
        self.status_code = status
        self.text = text
        self.url = url
        self.headers = {"Content-Type": ctype}


def _get(page):
    return lambda url, **kwargs: page


NO_SLEEP = {"sleep": lambda seconds: None}


class Sequence_:
    """Returns the given pages one after another, counting calls."""

    def __init__(self, *pages):
        self.pages = list(pages)
        self.calls = 0

    def __call__(self, url, **kwargs):
        self.calls += 1
        return self.pages[min(self.calls, len(self.pages)) - 1]


def test_ok_page_returns_final_url_and_real_text():
    result = check_url("https://example.com/a", get=_get(Page()), **NO_SLEEP)
    assert result.status == "ok" and result.final_url == "https://example.com/final"
    assert "How LOLA built live voice rooms." in result.text
    assert "Latency stayed under 300 ms." in result.text
    assert "var secret" not in result.text and "Menu Home" not in result.text and "Copyright" not in result.text


def test_404_and_410_are_dead():
    for status in (404, 410):
        assert check_url("https://example.com/a", get=_get(Page(status=status)), **NO_SLEEP).status == "dead"


def test_other_errors_are_unknown_not_dead():
    for status in (401, 403, 429, 500, 503):
        assert check_url("https://example.com/a", get=_get(Page(status=status)), **NO_SLEEP).status == "unknown"


def test_network_error_is_unknown():
    def boom(url, **kwargs):
        raise TimeoutError("slow")

    result = check_url("https://example.com/a", get=boom, **NO_SLEEP)
    assert result.status == "unknown" and result.final_url == "https://example.com/a"


def test_non_html_content_is_ok_without_text():
    result = check_url("https://example.com/a.pdf", get=_get(Page(text="%PDF", ctype="application/pdf")), **NO_SLEEP)
    assert result.status == "ok" and result.text == ""


def test_page_text_is_limited_and_collapses_whitespace():
    text = page_text("<title>T</title><p>" + ("word  \n " * 1000) + "</p>", limit=200)
    assert len(text) <= 200 and "  " not in text and "\n" not in text


def test_a_good_link_must_open_on_every_try():
    get = Sequence_(Page())
    assert check_url("https://example.com/a", get=get, attempts=3, **NO_SLEEP).status == "ok"
    assert get.calls == 3


def test_a_link_that_404s_on_any_try_is_unreliable_and_counts_as_dead():
    # agora.io was seen answering 404 for a page that opens on other tries
    get = Sequence_(Page(), Page(), Page(status=404))
    assert check_url("https://example.com/a", get=get, attempts=3, **NO_SLEEP).status == "dead"


def test_a_dead_link_stops_after_the_first_404():
    get = Sequence_(Page(status=404), Page())
    assert check_url("https://example.com/a", get=get, attempts=3, **NO_SLEEP).status == "dead"
    assert get.calls == 1


def test_tries_are_spaced_out():
    waits = []
    check_url("https://example.com/a", get=Sequence_(Page()), attempts=3, sleep=waits.append)
    assert len(waits) == 2 and all(w > 0 for w in waits)


def test_mixed_ok_and_blocked_tries_still_count_as_ok():
    get = Sequence_(Page(), Page(status=429), Page())
    assert check_url("https://example.com/a", get=get, attempts=3, **NO_SLEEP).status == "ok"

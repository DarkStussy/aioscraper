from aioscraper._helpers.http import parse_url


def test_parse_url_updates_query_params():
    url = parse_url("https://example.com/path?q0=1", {"q1": "2"})

    assert str(url) == "https://example.com/path?q0=1&q1=2"

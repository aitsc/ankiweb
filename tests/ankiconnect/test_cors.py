from ankiweb.ankiconnect.cors import allow_origin


def test_star_allows_all():
    allowed, header = allow_origin("https://evil.example", ["*"])
    assert allowed and header == "*"


def test_exact_match():
    allowed, header = allow_origin("http://localhost", ["http://localhost"])
    assert allowed and header == "http://localhost"


def test_localhost_implies_127():
    allowed, header = allow_origin("http://127.0.0.1:5000", ["http://localhost"])
    assert allowed and header == "http://127.0.0.1:5000"


def test_localhost_with_port_and_https_allowed():
    assert allow_origin("http://localhost:8080", ["http://localhost"])[0]
    assert allow_origin("https://localhost", ["http://localhost"])[0]


def test_extension_origins_allowed_when_localhost_listed():
    allowed, _ = allow_origin("chrome-extension://abc", ["http://localhost"])
    assert allowed


def test_no_origin_allowed():
    allowed, _ = allow_origin(None, ["http://localhost"])
    assert allowed


def test_disallowed():
    allowed, _ = allow_origin("https://evil.example", ["http://localhost"])
    assert not allowed

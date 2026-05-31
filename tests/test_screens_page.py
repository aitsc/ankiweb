from ankiweb.screens.page import render_page


def test_render_page_structure():
    html = render_page("deckbrowser", "<div id=body>hi</div>", ["css/deckbrowser.css"])
    assert "<!doctype html>" in html.lower()
    assert 'window.__ankiwebContext="deckbrowser"' in html
    assert '/_anki/css/deckbrowser.css' in html
    assert '/shell/static/bootstrap.js' in html
    assert "<div id=body>hi</div>" in html
    # context script must come before the bootstrap script so the Bridge picks it up
    assert html.index("__ankiwebContext") < html.index("bootstrap.js")

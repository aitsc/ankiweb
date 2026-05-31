from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "ankiweb" / "web_assets"


def test_required_assets_vendored():
    for rel in ["js/reviewer.js", "css/reviewer.css", "sveltekit/index.html",
                "js/vendor/jquery.min.js", "VERSION"]:
        assert (ASSETS / rel).exists(), f"missing {rel}"
    assert (ASSETS / "VERSION").read_text().strip() == "25.9.4"

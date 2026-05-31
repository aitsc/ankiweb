from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "ankiweb" / "web_assets"

import pytest
pytestmark = pytest.mark.skipif(not ASSETS.exists(), reason="run tools/fetch_web_assets.py first")


def test_required_assets_vendored():
    for rel in ["js/reviewer.js", "css/reviewer.css", "sveltekit/index.html",
                "js/vendor/jquery.min.js", "VERSION"]:
        assert (ASSETS / rel).exists(), f"missing {rel}"
    assert (ASSETS / "VERSION").read_text().strip() == "25.9.4"

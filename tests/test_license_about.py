from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app
from ankiweb.screens.page import render_page


def _client(tmp_path, source_url=""):
    s = Settings(collection_path=tmp_path / "c.anki2", source_url=source_url)
    return TestClient(create_app(s))


def test_about_offers_source_and_agpl(tmp_path: Path):
    with _client(tmp_path) as c:
        r = c.get("/about")
        assert r.status_code == 200
        assert "AGPL-3.0-or-later" in r.text or "Affero" in r.text
        assert "github.com/ankitects/anki" in r.text
        assert "github.com/FooSoft/anki-connect" in r.text
        # no source configured → tells the operator to set the env var
        assert "ANKIWEB_SOURCE_URL" in r.text


def test_about_shows_configured_source(tmp_path: Path):
    with _client(tmp_path, source_url="https://example.com/my/ankiweb") as c:
        r = c.get("/about")
        assert "https://example.com/my/ankiweb" in r.text


def test_toolbar_has_source_link():
    html = render_page("deckbrowser", "<div>x</div>")
    assert "href='/about'" in html and ">Source</a>" in html


def test_license_files_present():
    root = Path(__file__).resolve().parent.parent
    assert (root / "LICENSE").read_text().startswith("                    GNU AFFERO GENERAL PUBLIC LICENSE")
    assert (root / "LICENSES" / "GPL-3.0-or-later.txt").exists()
    assert "AGPL-3.0-or-later" in (root / "THIRD-PARTY-NOTICES.md").read_text()

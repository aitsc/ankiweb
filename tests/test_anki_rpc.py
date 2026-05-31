import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app
from ankiweb.anki_rpc.passthrough import camel_to_snake, snake_to_camel


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "collection.anki2")
    with TestClient(create_app(settings)) as c:
        yield c


def test_name_mapping_roundtrip():
    assert camel_to_snake("getDeckConfigsForUpdate") == "get_deck_configs_for_update"
    assert camel_to_snake("i18nResources") == "i18n_resources"  # digit-run regression guard
    assert camel_to_snake("cardStats") == "card_stats"
    assert snake_to_camel("i18n_resources") == "i18nResources"
    assert snake_to_camel("get_note") == "getNote"


def test_i18n_resources_passthrough(client):
    r = client.post("/_anki/i18nResources", content=b"",
                    headers={"Content-Type": "application/binary"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/binary"
    assert len(r.content) > 0


def test_content_type_guard(client):
    r = client.post("/_anki/i18nResources", content=b"",
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 403


def test_unknown_method_404(client):
    r = client.post("/_anki/doesNotExist", content=b"",
                    headers={"Content-Type": "application/binary"})
    assert r.status_code == 404


def test_save_custom_colours(client):
    # empty body is a valid no-op write; returns 204
    r = client.post("/_anki/saveCustomColours", content=b"",
                    headers={"Content-Type": "application/binary"})
    assert r.status_code == 204

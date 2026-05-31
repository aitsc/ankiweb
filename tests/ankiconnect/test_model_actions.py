import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.ankiconnect.app import create_ankiconnect_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_ankiconnect_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _call(client, action, **params):
    r = client.post("/", json={"action": action, "version": 6, "params": params})
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None, body["error"]
    return body["result"]


def test_model_names(client):
    assert "Basic" in _call(client, "modelNames")


def test_model_names_and_ids(client):
    nai = _call(client, "modelNamesAndIds")
    assert "Basic" in nai and isinstance(nai["Basic"], int)


def test_model_field_names(client):
    assert _call(client, "modelFieldNames", modelName="Basic") == ["Front", "Back"]


def test_model_templates(client):
    tmpls = _call(client, "modelTemplates", modelName="Basic")
    name = list(tmpls.keys())[0]
    assert "Front" in tmpls[name] and "Back" in tmpls[name]


def test_model_styling(client):
    assert "css" in _call(client, "modelStyling", modelName="Basic")


def test_model_field_fonts(client):
    fonts = _call(client, "modelFieldFonts", modelName="Basic")
    assert "Front" in fonts and "font" in fonts["Front"] and "size" in fonts["Front"]


def test_model_name_from_id_and_find(client):
    mid = _call(client, "modelNamesAndIds")["Basic"]
    assert _call(client, "modelNameFromId", modelId=mid) == "Basic"
    found = _call(client, "findModelsByName", modelNames=["Basic"])
    assert found[0]["name"] == "Basic"
    assert _call(client, "findModelsById", modelIds=[mid])[0]["id"] == mid


def test_model_fields_on_templates(client):
    res = _call(client, "modelFieldsOnTemplates", modelName="Basic")
    name = list(res.keys())[0]
    # Card 1: front refs == ["Front"]; back side strips FrontSide and de-dupes Front -> []
    assert res[name][0] == ["Front"]
    assert "FrontSide" not in res[name][1]


def test_find_models_missing_raises(client):
    # reference RAISES on a missing model (never returns null entries)
    for action, kw in (("findModelsByName", {"modelNames": ["NoSuchModel"]}),
                       ("findModelsById", {"modelIds": [123]}),
                       ("modelNameFromId", {"modelId": 123})):
        r = client.post("/", json={"action": action, "version": 6, "params": kw})
        assert r.json()["error"] is not None

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


def test_create_model(client):
    res = _call(client, "createModel", modelName="MyModel",
                inOrderFields=["A", "B"],
                cardTemplates=[{"Name": "C1", "Front": "{{A}}", "Back": "{{FrontSide}}<hr>{{B}}"}],
                css=".card{color:red}")
    assert res["name"] == "MyModel"
    assert _call(client, "modelFieldNames", modelName="MyModel") == ["A", "B"]
    assert _call(client, "modelTemplates", modelName="MyModel")["C1"]["Front"] == "{{A}}"
    assert "color:red" in _call(client, "modelStyling", modelName="MyModel")["css"]


def test_create_cloze_model(client):
    _call(client, "createModel", modelName="MyCloze", inOrderFields=["Text"],
          cardTemplates=[{"Front": "{{cloze:Text}}", "Back": "{{cloze:Text}}"}], isCloze=True)
    assert _call(client, "findModelsByName", modelNames=["MyCloze"])[0]["type"] == 1


def test_update_model_templates_and_styling(client):
    _call(client, "createModel", modelName="UM", inOrderFields=["A"],
          cardTemplates=[{"Name": "C1", "Front": "{{A}}", "Back": "{{A}}"}])
    assert _call(client, "updateModelTemplates",
                 model={"name": "UM", "templates": {"C1": {"Front": "Q:{{A}}", "Back": "X"}}}) is None
    assert _call(client, "modelTemplates", modelName="UM")["C1"]["Front"] == "Q:{{A}}"
    assert _call(client, "updateModelStyling", model={"name": "UM", "css": ".x{}"}) is None
    assert _call(client, "modelStyling", modelName="UM")["css"] == ".x{}"


def test_find_and_replace_in_models(client):
    _call(client, "createModel", modelName="FR", inOrderFields=["A"],
          cardTemplates=[{"Name": "C1", "Front": "HELLO HELLO {{A}}", "Back": "{{A}}"}])
    # returns the count of MODELS updated (==1), NOT the 2 occurrences replaced
    n = _call(client, "findAndReplaceInModels", modelName="FR",
              findText="HELLO", replaceText="HI", front=True, back=False, css=False)
    assert n == 1
    assert "HI HI" in _call(client, "modelTemplates", modelName="FR")["C1"]["Front"]


def test_create_model_guards(client):
    # duplicate name, empty fields, and empty templates all raise (ref 1120-1127)
    dup = client.post("/", json={"action": "createModel", "version": 6, "params": {
        "modelName": "Basic", "inOrderFields": ["X"],
        "cardTemplates": [{"Name": "C", "Front": "{{X}}", "Back": "{{X}}"}]}})
    assert dup.json()["error"] is not None
    empty = client.post("/", json={"action": "createModel", "version": 6, "params": {
        "modelName": "EmptyOne", "inOrderFields": [], "cardTemplates": []}})
    assert empty.json()["error"] is not None


def _mk(client, name="MUT"):
    _call(client, "createModel", modelName=name, inOrderFields=["A", "B"],
          cardTemplates=[{"Name": "C1", "Front": "{{A}}", "Back": "{{B}}"}])
    return name


def test_field_mutators(client):
    m = _mk(client, "MF")
    assert _call(client, "modelFieldAdd", modelName=m, fieldName="C") is None
    assert "C" in _call(client, "modelFieldNames", modelName=m)
    assert _call(client, "modelFieldRename", modelName=m, oldFieldName="C", newFieldName="D") is None
    assert "D" in _call(client, "modelFieldNames", modelName=m)
    assert _call(client, "modelFieldReposition", modelName=m, fieldName="D", index=0) is None
    assert _call(client, "modelFieldNames", modelName=m)[0] == "D"
    assert _call(client, "modelFieldSetFont", modelName=m, fieldName="A", font="Courier") is None
    assert _call(client, "modelFieldFonts", modelName=m)["A"]["font"] == "Courier"
    assert _call(client, "modelFieldSetFontSize", modelName=m, fieldName="A", fontSize=30) is None
    assert _call(client, "modelFieldFonts", modelName=m)["A"]["size"] == 30
    assert _call(client, "modelFieldSetDescription", modelName=m, fieldName="A", description="d") is True
    assert "d" in _call(client, "modelFieldDescriptions", modelName=m)
    assert _call(client, "modelFieldRemove", modelName=m, fieldName="D") is None
    assert "D" not in _call(client, "modelFieldNames", modelName=m)


def test_template_mutators(client):
    m = _mk(client, "MT")
    assert _call(client, "modelTemplateAdd", modelName=m,
                 template={"Name": "C2", "Front": "{{B}}", "Back": "{{A}}"}) is None
    assert "C2" in _call(client, "modelTemplates", modelName=m)
    assert _call(client, "modelTemplateRename", modelName=m,
                 oldTemplateName="C2", newTemplateName="C3") is None
    assert "C3" in _call(client, "modelTemplates", modelName=m)
    assert _call(client, "modelTemplateReposition", modelName=m, templateName="C3", index=0) is None
    assert list(_call(client, "modelTemplates", modelName=m).keys())[0] == "C3"
    assert _call(client, "modelTemplateRemove", modelName=m, templateName="C3") is None
    assert "C3" not in _call(client, "modelTemplates", modelName=m)


def test_field_set_type_validation(client):
    m = _mk(client, "MV")
    bad = client.post("/", json={"action": "modelFieldSetFontSize", "version": 6,
                                 "params": {"modelName": m, "fieldName": "A", "fontSize": "big"}})
    assert bad.json()["error"] is not None

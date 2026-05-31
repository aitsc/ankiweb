# ankiweb AnkiConnect B3 — Models + Media Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The note-type (model) and media actions of the AnkiConnect API — introspect/create/modify note types and their fields/templates, and store/retrieve/list/delete media — plus the deferred `addNote` media fields (audio/video/picture), so clients like Yomitan can add cards with images/audio.

**Architecture:** More `@action` handlers in `ankiweb/ankiconnect/actions/{models,media}.py`, registered into the existing `ACTIONS` registry, over the shared `CollectionService`. Model mutators get the notetype dict (`col.models.by_name`), mutate via `col.models.{new_field,add_field,...}`, then persist with `col.models.update_dict` (broadcast via `run_emit`). Media uses `col.media.{write_data,dir,have,trash_files}`; URL downloads use `httpx` (sync, in the worker thread). `addNote`/`addNotes` gain media-field attachment.

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, `httpx` (already a dep), the B1/B2 AnkiConnect infra, pytest. Run via `conda run -n ankiweb ...`.

**This is Plan B3 of 4 for Sub-project B.** B4 = gui*. Spec: `docs/superpowers/specs/2026-06-01-ankiweb-ankiconnect-api-design.md`.

**Deliberate deferrals (NOT defects):** advanced field options beyond font/size/description; `exportPackage`/`importPackage` (need keyword-only `col.export_anki_package` proto options) → later; gui*/Statistics → B4/later. The minor B2 follow-ups (notesInfo/cardsInfo missing-id `{}` alignment, updateNote empty-guard) are **folded into Task 4 here** as a quick parity fix.

**Intentional divergence (verified vs reference):** Upstream AnkiConnect attaches media inside `createNote`, which `canAddNote`/`canAddNoteWithErrorDetail` also call — so a *can-add check* in real AnkiConnect has the side effect of writing media files to the collection. ankiweb deliberately attaches media ONLY in `addNote`/`addNotes` (a can-add probe stays side-effect-free). This is a conscious, safer divergence, not an oversight.

**Grounded anki 25.9.4 facts (verified live):** `col.models.all_names_and_ids()`→NotetypeNameId(.name/.id); `by_name(name)`/`get(id)`/`id_for_name(name)`→dict|None; `all()`; `field_names(nt)`; `field_map(nt)`→{name:(ord,FieldDict)}; `new(name)`→dict; `add_dict(nt)`→OpChangesWithId; `update_dict(nt, skip_checks=False)`→OpChanges; `remove(id)`→OpChanges; `new_field(name)`/`add_field(nt,fld)`/`remove_field(nt,fld)`/`rename_field(nt,fld,new)`/`reposition_field(nt,fld,idx)`; `new_template(name)`/`add_template(nt,tmpl)`/`remove_template(nt,tmpl)`/`reposition_template(nt,tmpl,idx)`. Model dict keys: `css,did,flds,id,latexPost,latexPre,latexsvg,mod,name,originalStockKind,req,sortf,tmpls,type,usn` (type 0=standard,1=cloze). `flds[i]`: `{name,ord,font,size,description,collapsed,rtl,sticky,plainText,...}`. `tmpls[i]`: `{name,qfmt,afmt,bqfmt,bafmt,ord,...}`. Media: `col.media.write_data(desired_fname, bytes)`→str (possibly renamed), `dir()`→str, `have(fname)`→bool, `trash_files([fnames])`, `add_file(path)`→str. NOTE: `col.models.by_name`/`get` return a CACHED dict — mutate it then `update_dict` (the aqt pattern; that's what AnkiConnect's save_model does).

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/ankiconnect/actions/models.py` (create) | all model/note-type actions |
| `ankiweb/ankiconnect/actions/media.py` (create) | media actions + `attach_media` helper |
| `ankiweb/ankiconnect/actions/notes.py` (modify) | `addNote`/`addNotes` call `attach_media`; missing-id `{}` for notesInfo/notesModTime; updateNote empty-guard |
| `ankiweb/ankiconnect/actions/cards.py` (modify) | missing-id `{}` for cardsInfo/cardsModTime |
| `ankiweb/ankiconnect/actions/__init__.py` (modify) | also import `models`, `media` |
| `tests/ankiconnect/test_model_actions.py`, `test_media_actions.py` (create) | tests |

---

## Task 1: Model read/introspection actions

**Files:**
- Create: `ankiweb/ankiconnect/actions/models.py`
- Modify: `ankiweb/ankiconnect/actions/__init__.py`
- Test: `tests/ankiconnect/test_model_actions.py`

- [ ] **Step 1: Write the failing test**

`tests/ankiconnect/test_model_actions.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_model_actions.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `models.py` (read actions)**

```python
from __future__ import annotations
import re
from ankiweb.ankiconnect.registry import action

_FIELD_REF = re.compile(r"\{\{[#/^]?(?:[a-zA-Z0-9_-]+:)*([^{}:#/^]+?)\}\}")


def _model_or_raise(col, name):
    m = col.models.by_name(name)
    if m is None:
        raise Exception("model was not found: " + str(name))
    return m


@action("modelNames")
async def model_names(rt):
    return await rt.service.run(lambda col: [m.name for m in col.models.all_names_and_ids()])


@action("modelNamesAndIds")
async def model_names_and_ids(rt):
    return await rt.service.run(
        lambda col: {m.name: m.id for m in col.models.all_names_and_ids()})


@action("modelFieldNames")
async def model_field_names(rt, modelName=None):
    return await rt.service.run(
        lambda col: [f["name"] for f in _model_or_raise(col, modelName)["flds"]])


@action("modelFieldDescriptions")
async def model_field_descriptions(rt, modelName=None):
    return await rt.service.run(
        lambda col: [f.get("description", "") for f in _model_or_raise(col, modelName)["flds"]])


@action("modelFieldFonts")
async def model_field_fonts(rt, modelName=None):
    def fn(col):
        return {f["name"]: {"font": f.get("font", "Arial"), "size": f.get("size", 20)}
                for f in _model_or_raise(col, modelName)["flds"]}
    return await rt.service.run(fn)


@action("modelTemplates")
async def model_templates(rt, modelName=None):
    def fn(col):
        return {t["name"]: {"Front": t["qfmt"], "Back": t["afmt"]}
                for t in _model_or_raise(col, modelName)["tmpls"]}
    return await rt.service.run(fn)


@action("modelStyling")
async def model_styling(rt, modelName=None):
    return await rt.service.run(lambda col: {"css": _model_or_raise(col, modelName)["css"]})


@action("modelFieldsOnTemplates")
async def model_fields_on_templates(rt, modelName=None):
    def _refs(fmt):  # field refs, minus the FrontSide special token
        return [r for r in _FIELD_REF.findall(fmt) if r != "FrontSide"]

    def fn(col):
        out = {}
        for t in _model_or_raise(col, modelName)["tmpls"]:
            q = _refs(t["qfmt"])
            a = [r for r in _refs(t["afmt"]) if r not in q]  # de-dupe vs question side
            out[t["name"]] = [q, a]
        return out
    return await rt.service.run(fn)


@action("findModelsById")
async def find_models_by_id(rt, modelIds=None):
    modelIds = modelIds or []

    def fn(col):
        out = []
        for mid in modelIds:
            m = col.models.get(int(mid))
            if m is None:
                raise Exception("model was not found: " + str(mid))
            out.append(m)
        return out
    return await rt.service.run(fn)


@action("findModelsByName")
async def find_models_by_name(rt, modelNames=None):
    modelNames = modelNames or []

    def fn(col):
        out = []
        for n in modelNames:
            m = col.models.by_name(n)
            if m is None:
                raise Exception("model was not found: " + str(n))
            out.append(m)
        return out
    return await rt.service.run(fn)


@action("modelNameFromId")
async def model_name_from_id(rt, modelId=None):
    def fn(col):
        m = col.models.get(int(modelId))
        if m is None:
            raise Exception("model was not found: " + str(modelId))
        return m["name"]
    return await rt.service.run(fn)
```

> **Fidelity (verified vs reference plugin 1173-1268):** `findModelsById`/`findModelsByName`/`modelNameFromId` RAISE `"model was not found: ..."` on a miss — they never return `None`/null entries. `modelFieldsOnTemplates` strips the `FrontSide` special token and de-dupes the answer-side list against the question side (ref 1259-1262). The `[front_refs, back_refs]` per-template shape is an ankiweb simplification (not byte-faithful to upstream's keyed shape), accepted for this scope.

- [ ] **Step 4: Update `actions/__init__.py`**

```python
from ankiweb.ankiconnect.actions import meta, decks, notes, cards, models, media  # noqa: F401
```
(Create an empty `ankiweb/ankiconnect/actions/media.py` stub now — `"""AnkiConnect media actions (filled in Task 4)."""` — so this import resolves; Task 4 fills it.)

- [ ] **Step 5: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_model_actions.py -v`
Expected: PASS. (`_FIELD_REF` strips cloze/conditional prefixes via the capture group; `modelFieldsOnTemplates` additionally drops `FrontSide` and de-dupes the back list against the front.)

- [ ] **Step 6: Commit**

```bash
git add ankiweb/ankiconnect/actions/models.py ankiweb/ankiconnect/actions/media.py ankiweb/ankiconnect/actions/__init__.py tests/ankiconnect/test_model_actions.py
git commit -m "feat(ankiconnect): model read/introspection actions"
```

## Context
Read-only model introspection over the model dict (`flds`/`tmpls`/`css`). `modelTemplates` returns `{tmplName:{Front:qfmt, Back:afmt}}`; `modelFieldsOnTemplates` extracts `{{Field}}` refs (regex capture strips cloze/conditional prefixes), then drops `FrontSide` and de-dupes the answer list against the question list. `findModelsBy*`/`modelNameFromId` return the raw model dict(s) and RAISE on a missing model (never null entries).

## Report Format
Report: Status, test results, files changed, self-review, commit SHA, concerns.

---

## Task 2: createModel + model update actions

**Files:**
- Modify: `ankiweb/ankiconnect/actions/models.py`
- Test: `tests/ankiconnect/test_model_actions.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
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
    # cloze model type is 1 (verify via findModelsByName)
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
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_model_actions.py -k "create_model or cloze or update_model or find_and_replace" -v`
Expected: FAIL.

- [ ] **Step 3: Implement (append to models.py)**

```python
from ankiweb.ankiconnect.actions._helpers import run_emit


@action("createModel")
async def create_model(rt, modelName=None, inOrderFields=None, cardTemplates=None,
                       css=None, isCloze=False):
    inOrderFields = inOrderFields or []
    cardTemplates = cardTemplates or []
    # Reference guards (plugin/__init__.py:1120-1127): reject empty field/template lists.
    if not inOrderFields:
        raise Exception("Must provide at least one field for inOrderFields")
    if not cardTemplates:
        raise Exception("Must provide at least one card for cardTemplates")

    def fn(col):
        if modelName in [m.name for m in col.models.all_names_and_ids()]:
            raise Exception("Model name already exists")  # ref 1126-1127
        m = col.models.new(modelName)
        for fname in inOrderFields:
            col.models.add_field(m, col.models.new_field(fname))
        for i, tmpl in enumerate(cardTemplates):
            t = col.models.new_template(tmpl.get("Name", "Card %d" % (i + 1)))
            t["qfmt"] = tmpl.get("Front", "")
            t["afmt"] = tmpl.get("Back", "")
            col.models.add_template(m, t)
        if css is not None:
            m["css"] = css
        if isCloze:
            m["type"] = 1
        op = col.models.add_dict(m)
        return col.models.get(op.id), op  # return the persisted model dict
    return await run_emit(rt, fn)


@action("updateModelTemplates")
async def update_model_templates(rt, model=None):
    model = model or {}

    def fn(col):
        m = _model_or_raise(col, model.get("name"))
        templates = model.get("templates") or {}
        for t in m["tmpls"]:
            if t["name"] in templates:
                upd = templates[t["name"]]
                if upd.get("Front"):   # ref ignores empty-string Front/Back (1305/1309)
                    t["qfmt"] = upd["Front"]
                if upd.get("Back"):
                    t["afmt"] = upd["Back"]
        return None, col.models.update_dict(m)
    await run_emit(rt, fn)
    return None


@action("updateModelStyling")
async def update_model_styling(rt, model=None):
    model = model or {}

    def fn(col):
        m = _model_or_raise(col, model.get("name"))
        m["css"] = model.get("css", "")
        return None, col.models.update_dict(m)
    await run_emit(rt, fn)
    return None


@action("findAndReplaceInModels")
async def find_and_replace_in_models(rt, modelName=None, findText=None, replaceText=None,
                                     front=True, back=True, css=True):
    # Reference returns the number of MODELS updated (ref 1328-1353), not the
    # occurrence count, and treats a falsy modelName as "all models".
    def _replace(m):
        changed = False
        for t in m["tmpls"]:
            if front and findText in t["qfmt"]:
                t["qfmt"] = t["qfmt"].replace(findText, replaceText)
                changed = True
            if back and findText in t["afmt"]:
                t["afmt"] = t["afmt"].replace(findText, replaceText)
                changed = True
        if css and findText in m["css"]:
            m["css"] = m["css"].replace(findText, replaceText)
            changed = True
        return changed

    def fn(col):
        if modelName:
            models = [_model_or_raise(col, modelName)]
        else:
            models = [col.models.get(nt.id) for nt in col.models.all_names_and_ids()]
        updated = 0
        last_op = None
        for m in models:
            if _replace(m):
                last_op = col.models.update_dict(m)
                updated += 1
        return updated, last_op  # run_emit tolerates last_op None (no model changed)
    return await run_emit(rt, fn)
```

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_model_actions.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ankiweb/ankiconnect/actions/models.py tests/ankiconnect/test_model_actions.py
git commit -m "feat(ankiconnect): createModel + model update actions"
```

## Context
`createModel` builds a notetype (fields via `new_field`/`add_field`, templates via `new_template`/`add_template` with qfmt=Front/afmt=Back, css, type=1 for cloze), `add_dict`, returns the persisted dict. Update actions mutate the cached dict then `update_dict` (broadcast via run_emit).

## Report Format
Report: Status, test results, files changed, self-review, commit SHA, concerns.

---

## Task 3: Model template + field mutators

**Files:**
- Modify: `ankiweb/ankiconnect/actions/models.py`
- Test: `tests/ankiconnect/test_model_actions.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_model_actions.py -k "field_mutators or template_mutators" -v`
Expected: FAIL.

- [ ] **Step 3: Implement (append to models.py)**

```python
def _field_or_raise(m, name):
    for f in m["flds"]:
        if f["name"] == name:
            return f
    raise Exception("field was not found: " + str(name))


def _template_or_raise(m, name):
    for t in m["tmpls"]:
        if t["name"] == name:
            return t
    raise Exception("template was not found: " + str(name))


@action("modelTemplateAdd")
async def model_template_add(rt, modelName=None, template=None):
    template = template or {}
    name = template["Name"]   # ref requires Name/Front/Back (1377-1397); KeyError if absent
    front = template["Front"]
    back = template["Back"]

    def fn(col):
        m = _model_or_raise(col, modelName)
        for t in m["tmpls"]:        # update-in-place if a template with this name exists
            if t["name"] == name:
                t["qfmt"] = front
                t["afmt"] = back
                return None, col.models.update_dict(m)
        t = col.models.new_template(name)
        t["qfmt"] = front
        t["afmt"] = back
        col.models.add_template(m, t)
        return None, col.models.update_dict(m)
    await run_emit(rt, fn)
    return None


@action("modelTemplateRemove")
async def model_template_remove(rt, modelName=None, templateName=None):
    def fn(col):
        m = _model_or_raise(col, modelName)
        col.models.remove_template(m, _template_or_raise(m, templateName))
        return None, col.models.update_dict(m)
    await run_emit(rt, fn)
    return None


@action("modelTemplateRename")
async def model_template_rename(rt, modelName=None, oldTemplateName=None, newTemplateName=None):
    def fn(col):
        m = _model_or_raise(col, modelName)
        _template_or_raise(m, oldTemplateName)["name"] = newTemplateName
        return None, col.models.update_dict(m)
    await run_emit(rt, fn)
    return None


@action("modelTemplateReposition")
async def model_template_reposition(rt, modelName=None, templateName=None, index=None):
    def fn(col):
        m = _model_or_raise(col, modelName)
        col.models.reposition_template(m, _template_or_raise(m, templateName), int(index))
        return None, col.models.update_dict(m)
    await run_emit(rt, fn)
    return None


@action("modelFieldAdd")
async def model_field_add(rt, modelName=None, fieldName=None, index=None):
    def fn(col):
        m = _model_or_raise(col, modelName)
        f = col.models.new_field(fieldName)
        col.models.add_field(m, f)
        if index is not None:
            col.models.reposition_field(m, f, int(index))
        return None, col.models.update_dict(m)
    await run_emit(rt, fn)
    return None


@action("modelFieldRemove")
async def model_field_remove(rt, modelName=None, fieldName=None):
    def fn(col):
        m = _model_or_raise(col, modelName)
        col.models.remove_field(m, _field_or_raise(m, fieldName))
        return None, col.models.update_dict(m)
    await run_emit(rt, fn)
    return None


@action("modelFieldRename")
async def model_field_rename(rt, modelName=None, oldFieldName=None, newFieldName=None):
    def fn(col):
        m = _model_or_raise(col, modelName)
        col.models.rename_field(m, _field_or_raise(m, oldFieldName), newFieldName)
        return None, col.models.update_dict(m)
    await run_emit(rt, fn)
    return None


@action("modelFieldReposition")
async def model_field_reposition(rt, modelName=None, fieldName=None, index=None):
    def fn(col):
        m = _model_or_raise(col, modelName)
        col.models.reposition_field(m, _field_or_raise(m, fieldName), int(index))
        return None, col.models.update_dict(m)
    await run_emit(rt, fn)
    return None


@action("modelFieldSetFont")
async def model_field_set_font(rt, modelName=None, fieldName=None, font=None):
    if not isinstance(font, str):   # ref 1469-1470
        raise Exception("font should be a string")

    def fn(col):
        m = _model_or_raise(col, modelName)
        _field_or_raise(m, fieldName)["font"] = font
        return None, col.models.update_dict(m)
    await run_emit(rt, fn)
    return None


@action("modelFieldSetFontSize")
async def model_field_set_font_size(rt, modelName=None, fieldName=None, fontSize=None):
    if not isinstance(fontSize, int) or isinstance(fontSize, bool):   # ref 1483-1484
        raise Exception("fontSize should be an integer")

    def fn(col):
        m = _model_or_raise(col, modelName)
        _field_or_raise(m, fieldName)["size"] = fontSize
        return None, col.models.update_dict(m)
    await run_emit(rt, fn)
    return None


@action("modelFieldSetDescription")
async def model_field_set_description(rt, modelName=None, fieldName=None, description=None):
    if not isinstance(description, str):   # ref 1497-1498
        raise Exception("description should be a string")

    def fn(col):
        m = _model_or_raise(col, modelName)
        _field_or_raise(m, fieldName)["description"] = description
        return True, col.models.update_dict(m)  # 25.9.4 always has the 'description' key
    return await run_emit(rt, fn)
```

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_model_actions.py -v`
Expected: PASS. (If `reposition_field`/`reposition_template` after add behaves unexpectedly, introspect — the helpers take `(notetype, field/template, idx)` and reorder; verify the resulting order. `modelTemplateRename` mutates `t["name"]` directly, which `update_dict` persists.)

- [ ] **Step 5: Commit**

```bash
git add ankiweb/ankiconnect/actions/models.py tests/ankiconnect/test_model_actions.py
git commit -m "feat(ankiconnect): model template + field mutators"
```

## Context
11 mutators: locate the field/template in the cached model dict by name, mutate via `col.models.{new_field,add_field,remove_field,rename_field,reposition_field,new_template,add_template,remove_template,reposition_template}` or direct dict edits (font/size/description, template rename), then `update_dict`. All broadcast via run_emit. `modelFieldSetDescription` returns True (others null).

## Report Format
Report: Status, test results, files changed, self-review, commit SHA, concerns.

---

## Task 4: Media actions + addNote media fields + B2 missing-id parity

**Files:**
- Modify: `ankiweb/ankiconnect/actions/media.py` (the stub), `ankiweb/ankiconnect/actions/notes.py`, `ankiweb/ankiconnect/actions/cards.py`
- Test: `tests/ankiconnect/test_media_actions.py`

- [ ] **Step 1: Write the failing test**

`tests/ankiconnect/test_media_actions.py`:
```python
import base64
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


def test_store_and_retrieve_media_base64(client):
    data = base64.b64encode(b"hello-bytes").decode()
    fname = _call(client, "storeMediaFile", filename="hi.txt", data=data)
    assert fname == "hi.txt"
    assert _call(client, "retrieveMediaFile", filename="hi.txt") == data
    assert "hi.txt" in _call(client, "getMediaFilesNames", pattern="*.txt")
    assert isinstance(_call(client, "getMediaDirPath"), str)
    assert _call(client, "deleteMediaFile", filename="hi.txt") is None
    assert _call(client, "retrieveMediaFile", filename="hi.txt") is False


def test_store_media_from_path(client, tmp_path):
    p = tmp_path / "src.txt"
    p.write_bytes(b"frompath")
    fname = _call(client, "storeMediaFile", filename="p.txt", path=str(p))
    assert fname == "p.txt"
    assert base64.b64decode(_call(client, "retrieveMediaFile", filename="p.txt")) == b"frompath"


def test_add_note_with_picture_field(client):
    data = base64.b64encode(b"\x89PNG-fake").decode()
    nid = _call(client, "addNote", note={
        "deckName": "Default", "modelName": "Basic",
        "fields": {"Front": "q", "Back": ""},
        "picture": [{"filename": "img.png", "data": data, "fields": ["Back"]}],
    })
    info = _call(client, "notesInfo", notes=[nid])[0]
    assert '<img src="img.png">' in info["fields"]["Back"]["value"]


def test_store_media_skip_hash_short_circuits(client):
    import hashlib
    raw = b"skip-me"
    data = base64.b64encode(raw).decode()
    h = hashlib.md5(raw).hexdigest()
    # matching skipHash -> returns None and writes nothing
    assert _call(client, "storeMediaFile", filename="sk.txt", data=data, skipHash=h) is None
    assert "sk.txt" not in _call(client, "getMediaFilesNames", pattern="*.txt")


def test_add_note_picture_single_object_and_unknown_field(client):
    # picture may be a single object (not a list); a target field absent from the
    # model is ignored rather than fabricated.
    data = base64.b64encode(b"\x89PNG").decode()
    nid = _call(client, "addNote", note={
        "deckName": "Default", "modelName": "Basic",
        "fields": {"Front": "q", "Back": ""},
        "picture": {"filename": "one.png", "data": data, "fields": ["Back", "Nope"]},
    })
    info = _call(client, "notesInfo", notes=[nid])[0]
    assert '<img src="one.png">' in info["fields"]["Back"]["value"]
    assert "Nope" not in info["fields"]


def test_notes_info_missing_id_appends_empty(client):
    # B2 parity fix: a missing id yields {} (positional), not an error
    res = _call(client, "notesInfo", notes=[999999999])
    assert res == [{}]
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_media_actions.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `media.py`**

```python
from __future__ import annotations
import base64
import fnmatch
import hashlib
import os
from ankiweb.ankiconnect.registry import action


def _fetch_bytes(data=None, path=None, url=None):
    if data is not None:
        return base64.b64decode(data)
    if path is not None:
        with open(path, "rb") as f:
            return f.read()
    if url is not None:
        import httpx
        return httpx.get(url, follow_redirects=True, timeout=30).content
    raise Exception("storeMediaFile requires one of data/path/url")


def _store(col, filename, data=None, path=None, url=None, skipHash=None, deleteExisting=True):
    """Returns the stored filename (possibly renamed), or None if skipHash matched."""
    raw = _fetch_bytes(data, path, url)
    if skipHash is not None and hashlib.md5(raw).hexdigest() == skipHash:
        return None  # ref 702-710: caller already has an identical file
    if deleteExisting:
        col.media.trash_files([filename])  # ref 711-712: delete-then-write
    return col.media.write_data(filename, raw)


@action("storeMediaFile")
async def store_media_file(rt, filename=None, data=None, path=None, url=None,
                           skipHash=None, deleteExisting=True):
    return await rt.service.run(
        lambda col: _store(col, filename, data, path, url, skipHash, deleteExisting))


@action("retrieveMediaFile")
async def retrieve_media_file(rt, filename=None):
    def fn(col):
        safe = os.path.basename(filename or "")   # ref normalizes; prevents '../' traversal
        full = os.path.join(col.media.dir(), safe)
        if not safe or not os.path.exists(full):
            return False
        with open(full, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return await rt.service.run(fn)


@action("getMediaFilesNames")
async def get_media_files_names(rt, pattern="*"):
    def fn(col):
        names = os.listdir(col.media.dir())
        return [n for n in names if fnmatch.fnmatch(n, pattern)]
    return await rt.service.run(fn)


@action("getMediaDirPath")
async def get_media_dir_path(rt):
    return await rt.service.run(lambda col: col.media.dir())


@action("deleteMediaFile")
async def delete_media_file(rt, filename=None):
    await rt.service.run(lambda col: col.media.trash_files([filename]))
    return None


# --- media-field attachment for addNote/addNotes (called from notes.py) ---
def attach_media(col, spec):
    """Store any audio/video/picture media in the note spec and append the right HTML
    into the target fields of spec['fields'] (mutates spec['fields'] in place). Only
    appends to fields that actually exist on the note's model (ref addMedia 769-800)."""
    fields = spec.setdefault("fields", {})
    model = col.models.by_name(spec.get("modelName", ""))
    valid = set(col.models.field_names(model)) if model else None
    for kind, tmpl in (("picture", '<img src="%s">'), ("audio", "[sound:%s]"),
                       ("video", "[sound:%s]")):
        media_list = spec.get(kind) or []
        if isinstance(media_list, dict):   # AnkiConnect accepts a single object too (ref 773-776)
            media_list = [media_list]
        for media in media_list:
            stored = _store(col, media["filename"], media.get("data"), media.get("path"),
                            media.get("url"), media.get("skipHash"))
            fname = stored if stored is not None else media["filename"]
            html = tmpl % fname
            for field_name in media.get("fields") or []:
                if valid is not None and field_name not in valid:
                    continue  # ref only writes fields present on the model (790)
                fields[field_name] = (fields.get(field_name, "") or "") + html
```

- [ ] **Step 4: Wire media into addNote/addNotes + the B2 missing-id parity fixes**

These are exact edits to the EXISTING `notes.py`/`cards.py` (do not invent new structure — match the snippets below).

**`ankiweb/ankiconnect/actions/notes.py`:**

(a) Add the import near the top (after the existing `_helpers` import):
```python
from ankiweb.ankiconnect.actions.media import attach_media
```

(b) `add_note` — `spec` is already bound (`spec = note or {}`). Add `attach_media(col, spec)` as the FIRST line of `fn(col)`, before `build_note`:
```python
    def fn(col):
        attach_media(col, spec)
        n, _ = build_note(col, spec)
        ...  # rest unchanged
```

(c) `add_notes` — bind `spec` once per iteration (avoids `spec or {}` evaluating to two different dicts when an entry is None, which would drop media), then attach before build. Replace the start of the loop body:
```python
        for spec in specs:
            try:
                spec = spec or {}
                attach_media(col, spec)
                n, _ = build_note(col, spec)
                ok, err = check_addable(col, n, spec.get("options"))
                if not ok:
                    raise Exception(err)
                did = col.decks.id(spec.get("deckName", "Default"))
                last_op = col.add_note(n, did)
                added_ids.append(n.id)
            except Exception as e:
                errs.append(str(e))
```
(Leave `canAddNote`/`canAddNoteWithErrorDetail` UNCHANGED — see the divergence note in Context.)

(d) `notesInfo` missing-id parity — keep the existing `ids = ...` line (the `query=` path depends on it); replace ONLY the return-comprehension:
```python
@action("notesInfo")
async def notes_info(rt, notes=None, query=None):
    def fn(col):
        ids = list(notes) if notes is not None else list(col.find_notes(query or ""))
        out = []
        for nid in ids:
            try:
                out.append(note_to_info(col, col.get_note(nid)))
            except Exception:
                out.append({})
        return out
    return await rt.service.run(fn)
```

(e) `notesModTime` missing-id parity — this is currently a lambda comprehension; rewrite into a `def fn` loop:
```python
@action("notesModTime")
async def notes_mod_time(rt, notes=None):
    notes = notes or []

    def fn(col):
        out = []
        for nid in notes:
            try:
                out.append({"noteId": nid, "mod": col.get_note(nid).mod})
            except Exception:
                out.append({})
        return out
    return await rt.service.run(fn)
```

(f) `updateNote` empty-guard — add at the top of `update_note` (after `spec = note or {}`):
```python
    if "fields" not in spec and "tags" not in spec:
        raise Exception('Must provide a "fields" or "tags" property.')
```

**`ankiweb/ankiconnect/actions/cards.py`:** both `cardsInfo` and `cardsModTime` are currently lambda comprehensions; rewrite each into a `def fn` loop appending `{}` on a missing id:
```python
@action("cardsInfo")
async def cards_info(rt, cards=None):
    cards = cards or []

    def fn(col):
        out = []
        for cid in cards:
            try:
                out.append(card_to_info(col, col.get_card(cid)))
            except Exception:
                out.append({})
        return out
    return await rt.service.run(fn)


@action("cardsModTime")
async def cards_mod_time(rt, cards=None):
    cards = cards or []

    def fn(col):
        out = []
        for cid in cards:
            try:
                out.append({"cardId": cid, "mod": col.get_card(cid).mod})
            except Exception:
                out.append({})
        return out
    return await rt.service.run(fn)
```

- [ ] **Step 5: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_media_actions.py tests/ankiconnect/test_note_actions.py tests/ankiconnect/test_card_actions.py -v`
Then full suite: `conda run -n ankiweb python -m pytest -q`.
Expected: PASS. (`write_data` may rename on hash collision; the tests use unique names so the returned name == requested. `retrieveMediaFile` returns base64 of the file bytes; for base64-stored data the round-trip equals the input base64.)

- [ ] **Step 6: Commit**

```bash
git add ankiweb/ankiconnect/actions/media.py ankiweb/ankiconnect/actions/notes.py ankiweb/ankiconnect/actions/cards.py tests/ankiconnect/test_media_actions.py
git commit -m "feat(ankiconnect): media actions + addNote media fields + missing-id {} parity"
```

## Context
Media: `storeMediaFile` accepts base64 `data` / local `path` / `url` (httpx, sync in the worker thread), honors `skipHash` (md5 match → return None, no write) and `deleteExisting` (delete-then-write); `retrieveMediaFile` base64-encodes the file (or False if missing), normalizing the filename to its basename; `getMediaFilesNames` globs the media dir; `deleteMediaFile` → `trash_files`. `attach_media` (the deferred B2 feature) stores picture/audio/video media (accepts a single object or a list) and appends `<img src>` / `[sound:]` HTML into the target fields that exist on the model — called from addNote/addNotes only (see the Intentional divergence note re: canAdd). Also folds in the B2 missing-id `{}` parity for notesInfo/notesModTime/cardsInfo/cardsModTime and the updateNote empty-guard.

## Report Format
Report: Status, test results (media + note + card + full suite), files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (B3 = Models + Media from spec §2):** Models read (Task 1): modelNames/...AndIds/modelFieldNames/...Descriptions/...Fonts/modelFieldsOnTemplates/modelTemplates/modelStyling/findModelsBy{Id,Name}/modelNameFromId. createModel + updates (Task 2): createModel/updateModelTemplates/updateModelStyling/findAndReplaceInModels. Mutators (Task 3): modelTemplate{Add,Remove,Rename,Reposition}, modelField{Add,Remove,Rename,Reposition,SetFont,SetFontSize,SetDescription}. Media (Task 4): storeMediaFile/retrieveMediaFile/getMediaFilesNames/getMediaDirPath/deleteMediaFile + addNote media fields + B2 missing-id parity. Deferred (documented): export/import, advanced field opts.

**2. Placeholder scan:** No TBD/TODO. The Task-3 reposition note is verify-and-adjust (anki-api agent confirmed reposition works after add + update_dict).

**3. Type/name consistency:** `_model_or_raise`/`_field_or_raise`/`_template_or_raise` (models.py); `run_emit`/`build_note`/`check_addable` (from _helpers, B2); `attach_media` (media.py) imported by notes.py. All actions `async def(rt, **params)` with kwargs matching AnkiConnect param names (modelName, inOrderFields, cardTemplates, css, isCloze, model, findText, replaceText, front, back, oldFieldName, newFieldName, fieldName, index, font, fontSize, description, oldTemplateName, newTemplateName, templateName, template, filename, data, path, url, pattern, skipHash, deleteExisting). `col.models.add_dict→OpChangesWithId` (op.id used by createModel; run_emit's `getattr(op,"changes",op)` handles it). `actions/__init__` imports meta/decks/notes/cards/models/media; media.py stub created in Task 1, filled in Task 4.

**4. Adversarial verification (3-agent Workflow, run against live anki 25.9.4 + reference plugin + existing codebase):** anki-api confirmed EVERY `col.models.*`/`col.media.*` call exists and behaves as assumed (cached-dict mutation persists; `add_dict`→`get(op.id)` works; reposition after add persists; cloze type=1 persists; media round-trip + collision-rename). consistency confirmed the run_emit (value, op) tuple chain, `OpChangesWithId.changes`/`.id`, the media.py-stub ordering, and NO circular import (media→registry only; notes→media; media never imports notes). The following contract gaps the contract agent found are NOW FIXED in this plan: createModel guards (empty fields/templates/duplicate name); findModels*/modelNameFromId raise on miss; findAndReplaceInModels returns models-updated count + all-models path; storeMediaFile skipHash/deleteExisting; retrieveMediaFile basename normalization; attach_media single-object + model-field restriction + skipHash; canAddNote divergence documented (not mis-stated); modelFieldsOnTemplates FrontSide strip+dedupe; updateModelTemplates empty-string ignore; modelTemplateAdd require-keys + update-in-place; modelFieldSet* type checks; the four B2 missing-id parity rewrites spelled out for the lambda-comprehension cases; the addNotes `spec or {}` double-eval nit. **Accepted as-is:** `CardTypeError` on a field-less/broken template is surfaced cleanly by the dispatcher (dispatch.py:30-31 envelopes `str(exc)`) — matching reference behavior with NO `skip_checks=True` (which would silently persist broken templates); the `[front_refs, back_refs]` shape of `modelFieldsOnTemplates` is an ankiweb simplification, not byte-faithful to upstream's keyed shape.

from __future__ import annotations
import re
from ankiweb.ankiconnect.registry import action
from ankiweb.ankiconnect.actions._helpers import run_emit

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

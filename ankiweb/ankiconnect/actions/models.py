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

"""Note-type extra actions."""
from __future__ import annotations
from ankiweb.ankiconnect.registry import extra_action
from ankiweb.ankiconnect.actions._helpers import run_emit
from ankiweb.ankiconnect.schemas.extra import DeleteModelParams


@extra_action("deleteModel", params=DeleteModelParams, returns=bool,
              summary="Delete an entire note type (only if no notes use it)")
async def delete_model(rt, modelName=None, modelId=None):
    """Delete a whole note type — the reverse of createModel. Refuses (error) if any note
    still uses it, or if it is the only remaining note type. ankiweb-original: reachable only
    at /extra_actions/deleteModel, never via the canonical POST /."""
    def fn(col):
        m = col.models.get(modelId) if modelId is not None else None
        if m is None and modelName:
            m = col.models.by_name(modelName)
        if m is None:
            raise Exception("model was not found: " + str(modelName if modelName else modelId))
        used = col.models.use_count(m)
        if used:
            raise Exception(
                f"cannot delete note type '{m['name']}': {used} note(s) still use it")
        if len(col.models.all_names_and_ids()) <= 1:
            raise Exception("cannot delete the only remaining note type")
        return True, col.models.remove(m["id"])
    return await run_emit(rt, fn)

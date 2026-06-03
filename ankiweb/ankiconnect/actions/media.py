from __future__ import annotations
import base64
import fnmatch
import hashlib
import os
from ankiweb.ankiconnect.registry import action
from ankiweb.ankiconnect.schemas.media import (
    StoreMediaFileParams, RetrieveMediaFileParams, GetMediaFilesNamesParams,
    GetMediaDirPathParams, DeleteMediaFileParams,
)


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


@action("storeMediaFile", params=StoreMediaFileParams, summary="Store a media file")
async def store_media_file(rt, filename=None, data=None, path=None, url=None,
                           skipHash=None, deleteExisting=True):
    return await rt.service.run(
        lambda col: _store(col, filename, data, path, url, skipHash, deleteExisting))


@action("retrieveMediaFile", params=RetrieveMediaFileParams, summary="Retrieve a media file")
async def retrieve_media_file(rt, filename=None):
    def fn(col):
        safe = os.path.basename(filename or "")   # ref normalizes; prevents '../' traversal
        full = os.path.join(col.media.dir(), safe)
        if not safe or not os.path.exists(full):
            return False
        with open(full, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return await rt.service.run(fn)


@action("getMediaFilesNames", params=GetMediaFilesNamesParams, returns=list[str],
        summary="List media filenames by pattern")
async def get_media_files_names(rt, pattern="*"):
    def fn(col):
        names = os.listdir(col.media.dir())
        return [n for n in names if fnmatch.fnmatch(n, pattern)]
    return await rt.service.run(fn)


@action("getMediaDirPath", params=GetMediaDirPathParams, returns=str,
        summary="Get the media folder path")
async def get_media_dir_path(rt):
    return await rt.service.run(lambda col: col.media.dir())


@action("deleteMediaFile", params=DeleteMediaFileParams, summary="Delete a media file")
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

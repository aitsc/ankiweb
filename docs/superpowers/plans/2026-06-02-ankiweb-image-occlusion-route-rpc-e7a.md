# ankiweb Plan E7a — Image Occlusion Route + RPC Wiring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the data plane for reusing Anki's vendored Image Occlusion SvelteKit route — serve `GET /image-occlusion/{path}`, passthrough the two IO read RPCs, and add three path-confined CUSTOM handlers (`getImageForOcclusion` read+touch, `addImageOcclusionNote` write+broadcast, `updateImageOcclusionNote` write+broadcast) — so the IO SPA can load images, create, and update IO notes. (Entry points + the upload flow + Playwright are E7b.)

**Architecture:** Add `GET /image-occlusion/{path:path}` to `build_sveltekit_router` (serves the same `sveltekit/index.html`; the SPA client-routes on `location.pathname`, branching `/^\d+/` → edit/noteId vs → add/imagePath). The IO read RPCs `get_image_occlusion_note` (note_id) and `get_image_occlusion_fields` (notetype_id) are **passthrough**. The path-bearing/write RPCs are **CUSTOM** (handlers take `(service, body, hub)` since E3): `getImageForOcclusion` confines `GetImageForOcclusionRequest.path` to the managed temp dir (reuse E6a's `import_tmp.is_within`) and `os.utime`-touches it (keeps an active drawing session's temp image fresh against the E6a GC); `addImageOcclusionNote` confines `AddImageOcclusionNoteRequest.image_path`, runs the backend, and broadcasts the returned `OpChanges`; `updateImageOcclusionNote` runs the backend (note-id; no path) and broadcasts. The add-mode flow hardcodes `notetype_id = 0`, which the backend resolves to the (default-shipped) "Image Occlusion" notetype — so **no notetype-id plumbing here**. (Ensuring the notetype exists is an E7b upload-side `service.run` call, not a CUSTOM RPC — the SPA never POSTs `addImageOcclusionNotetype`, and mediasrv doesn't expose it.)

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, the E1 `build_sveltekit_router`, the `anki_rpc` passthrough/CUSTOM mechanism, E6a's `import_tmp`, `anki.image_occlusion_pb2`, pytest. Run via `conda run -n ankiweb ...`.

**This is E7a of Sub-project E7** (image occlusion). Spec: `docs/superpowers/specs/2026-06-02-ankiweb-image-occlusion-e7-design.md`. Next: E7b (Add upload + deck-browser button + Edit browser-routing + Playwright).

**Grounded facts (live-probed + spec-verified):**
- The IO SvelteKit route `image-occlusion/[...imagePathOrNoteId]` is vendored (node `8.*.mjs`, fabric bundled); `image-occlusion` is already in `SVELTEKIT_PAGES` (`assets.py`) but has NO GET route. The SPA loads via `getImageForOcclusion(path)` (add) / `getImageOcclusionNote(noteId)` (edit) and saves via `addImageOcclusionNote({notetypeId:0, imagePath, …})` / `updateImageOcclusionNote({noteId, …})`. No pycmd/bridgeCommand in the route.
- Backend (all `*_raw` exist): `get_image_occlusion_note(note_id) -> GetImageOcclusionNoteResponse` (oneof `note`|`error`; `note.image_data`/`occlusions`/`header`/`back_extra`/`tags`/`image_file_name`/`occlude_inactive`), `get_image_occlusion_fields(notetype_id)` (backend-only), `add_image_occlusion_note(notetype_id, image_path, occlusions, header, back_extra, tags) -> OpChanges`, `update_image_occlusion_note(note_id, occlusions, header, back_extra, tags) -> OpChanges`.
- `add_image_occlusion_note`: `image_path` is an ABSOLUTE FILESYSTEM path (a bare relative name → `BackendIOError`); the backend reads it and copies the image into `col.media.dir()`, then creates the note. With `notetype_id=0` it self-resolves the IO notetype. Probed: `op.note=True`, `op.card=True`; image appears in media; a minimal occlusions string `{{c1::image-occlusion:rect:left=.1:top=.1:width=.2:height=.2}}` works.
- `col.get_image_occlusion_note(note_id=…)` IS a col method; returns the note inline. `update_image_occlusion_note` changes the header (round-trips).
- proto request fields (probed): `GetImageForOcclusionRequest{path}`, `AddImageOcclusionNoteRequest{image_path, occlusions, header, back_extra, tags, notetype_id}`, `UpdateImageOcclusionNoteRequest{note_id, occlusions, header, back_extra, tags}`.
- `import_tmp.is_within(settings, path)` + `import_tmp.dir(settings)` exist (E6a); `service.settings` exposes them. `camel_to_snake` maps `getImageForOcclusion→get_image_for_occlusion`, `addImageOcclusionNote→add_image_occlusion_note`, `updateImageOcclusionNote→update_image_occlusion_note`, `get_image_occlusion_note`/`get_image_occlusion_fields` unchanged.
- The dispatch (`anki_rpc/__init__.py`): `if method in CUSTOM → CUSTOM[method](service, body, get_hub())`; exception → 500 + str(exc); `b""` out → 204. The `update_deck_configs` handler (handlers.py) is the OpChanges-parse-and-emit template.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/assets.py` (modify) | `GET /image-occlusion/{path:path}` in `build_sveltekit_router` |
| `ankiweb/anki_rpc/passthrough.py` (modify) | add `get_image_occlusion_note`, `get_image_occlusion_fields` |
| `ankiweb/anki_rpc/handlers.py` (modify) | `_emit_opchanges` helper + CUSTOM `getImageForOcclusion`/`addImageOcclusionNote`/`updateImageOcclusionNote` |
| `tests/test_image_occlusion.py` (create) | route serves shell (note-id + path); membership; path-confinement in/out; touch-on-read; add round-trip; update round-trip |

---

## Task 1: the `/image-occlusion` route + IO RPC wiring

**Files:** Modify `ankiweb/assets.py`, `ankiweb/anki_rpc/passthrough.py`, `ankiweb/anki_rpc/handlers.py`; Test `tests/test_image_occlusion.py`.

- [ ] **Step 1: Write the failing tests** — `tests/test_image_occlusion.py`:
```python
import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app

# a minimal valid 1x1 PNG
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000154a24f1f0000000049454e44ae426082")
OCCL = "{{c1::image-occlusion:rect:left=.1:top=.1:width=.2:height=.2}}"
BIN = {"content-type": "application/binary"}


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "c.anki2",
                        import_tmp_dir=tmp_path / "import-tmp")
    with TestClient(create_app(settings)) as c:
        yield c


def _img_in_tmp(client, name="pic.png"):
    from ankiweb import import_tmp
    p = import_tmp.dir(client.app.state.service.settings) / name
    p.write_bytes(PNG)
    return str(p)


def test_route_serves_shell_for_path_and_noteid(client):
    for seg in ("123", "%2Ftmp%2Ffoo.png"):
        r = client.get(f"/image-occlusion/{seg}")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert "_app/immutable/entry" in r.text


def test_membership():
    from ankiweb.anki_rpc.passthrough import PASSTHROUGH
    from ankiweb.anki_rpc.handlers import CUSTOM
    assert "get_image_occlusion_note" in PASSTHROUGH
    assert "get_image_occlusion_fields" in PASSTHROUGH
    for m in ("getImageForOcclusion", "addImageOcclusionNote", "updateImageOcclusionNote"):
        assert m in CUSTOM


def test_get_image_for_occlusion_confinement(client):
    import anki.image_occlusion_pb2 as iopb
    p = _img_in_tmp(client)
    ok = client.post("/_anki/getImageForOcclusion",
                     content=iopb.GetImageForOcclusionRequest(path=p).SerializeToString(), headers=BIN)
    assert ok.status_code == 200
    bad = client.post("/_anki/getImageForOcclusion",
                      content=iopb.GetImageForOcclusionRequest(path="/etc/hostname").SerializeToString(), headers=BIN)
    assert bad.status_code == 500


def test_get_image_for_occlusion_touches_mtime(client):
    import anki.image_occlusion_pb2 as iopb
    p = _img_in_tmp(client, "touch.png")
    old = 100000.0
    os.utime(p, (old, old))
    client.post("/_anki/getImageForOcclusion",
                content=iopb.GetImageForOcclusionRequest(path=p).SerializeToString(), headers=BIN)
    assert os.path.getmtime(p) > old + 1000  # bumped toward now


def test_add_image_occlusion_note_round_trip(client):
    import anki.image_occlusion_pb2 as iopb
    svc = client.app.state.service
    p = _img_in_tmp(client, "add.png")
    before = client.portal.call(svc.run, lambda col: col.note_count())
    req = iopb.AddImageOcclusionNoteRequest(
        notetype_id=0, image_path=p, occlusions=OCCL, header="H", back_extra="B", tags=["io"])
    r = client.post("/_anki/addImageOcclusionNote", content=req.SerializeToString(), headers=BIN)
    assert r.status_code == 200
    after = client.portal.call(svc.run, lambda col: col.note_count())
    assert after == before + 1
    media = client.portal.call(svc.run, lambda col: os.listdir(col.media.dir()))
    assert any(f.endswith(".png") for f in media)


def test_add_rejects_path_outside_tmp(client):
    import anki.image_occlusion_pb2 as iopb
    req = iopb.AddImageOcclusionNoteRequest(
        notetype_id=0, image_path="/etc/passwd", occlusions=OCCL, header="", back_extra="", tags=[])
    r = client.post("/_anki/addImageOcclusionNote", content=req.SerializeToString(), headers=BIN)
    assert r.status_code == 500


def test_update_image_occlusion_note_round_trip(client):
    import anki.image_occlusion_pb2 as iopb
    svc = client.app.state.service
    p = _img_in_tmp(client, "upd.png")
    add = iopb.AddImageOcclusionNoteRequest(
        notetype_id=0, image_path=p, occlusions=OCCL, header="H1", back_extra="B", tags=[])
    client.post("/_anki/addImageOcclusionNote", content=add.SerializeToString(), headers=BIN)
    nid = client.portal.call(svc.run, lambda col: col.find_notes('note:"Image Occlusion"')[0])
    upd = iopb.UpdateImageOcclusionNoteRequest(
        note_id=nid, occlusions=OCCL, header="H2", back_extra="B", tags=[])
    r = client.post("/_anki/updateImageOcclusionNote", content=upd.SerializeToString(), headers=BIN)
    assert r.status_code == 200
    hdr = client.portal.call(svc.run, lambda col: col.get_image_occlusion_note(note_id=nid).note.header)
    assert hdr == "H2"
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_image_occlusion.py -v` → FAIL.

- [ ] **Step 3: Add the route** — in `ankiweb/assets.py` `build_sveltekit_router`, next to the import routes:
```python
    @router.get("/image-occlusion/{path:path}")
    def image_occlusion_page(path: str) -> Response:
        return FileResponse(index, media_type="text/html")
```

- [ ] **Step 4: Extend the passthrough** — in `ankiweb/anki_rpc/passthrough.py`, add to `PASSTHROUGH`:
```python
    "get_image_occlusion_note", "get_image_occlusion_fields",
```

- [ ] **Step 5: Add the CUSTOM handlers** — in `ankiweb/anki_rpc/handlers.py`:
```python
async def _emit_opchanges(service, out: bytes) -> None:
    """Parse a raw OpChanges reply and broadcast its flags (image-occlusion writes)."""
    try:
        from anki.collection_pb2 import OpChanges
        from ankiweb.collection_service import op_changes_to_flags
        op = OpChanges()
        op.ParseFromString(bytes(out))
        flags = op_changes_to_flags(op)
        if any(flags.values()):
            await service.emit(flags, "image-occlusion")
    except Exception:
        pass


async def get_image_for_occlusion(service, body: bytes, hub) -> bytes:
    import os
    import anki.image_occlusion_pb2 as iopb
    from ankiweb import import_tmp
    req = iopb.GetImageForOcclusionRequest()
    req.ParseFromString(bytes(body))
    if req.path and not import_tmp.is_within(service.settings, req.path):
        raise ValueError("image path not allowed")
    # touch-on-read: keep an in-progress drawing session's temp image fresh vs the GC
    try:
        if req.path and os.path.isfile(req.path):
            os.utime(req.path, None)
    except OSError:
        pass
    return await service.backend_raw("get_image_for_occlusion", body)


async def add_image_occlusion_note(service, body: bytes, hub) -> bytes:
    import anki.image_occlusion_pb2 as iopb
    from ankiweb import import_tmp
    req = iopb.AddImageOcclusionNoteRequest()
    req.ParseFromString(bytes(body))
    if not import_tmp.is_within(service.settings, req.image_path):
        raise ValueError("image path not allowed")
    out = await service.backend_raw("add_image_occlusion_note", body)
    await _emit_opchanges(service, out)
    return out


async def update_image_occlusion_note(service, body: bytes, hub) -> bytes:
    out = await service.backend_raw("update_image_occlusion_note", body)
    await _emit_opchanges(service, out)
    return out


CUSTOM["getImageForOcclusion"] = get_image_for_occlusion
CUSTOM["addImageOcclusionNote"] = add_image_occlusion_note
CUSTOM["updateImageOcclusionNote"] = update_image_occlusion_note
```

- [ ] **Step 6: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_image_occlusion.py -v`, then regression: `conda run -n ankiweb python -m pytest tests/test_anki_rpc.py tests/test_import_rpc.py tests/test_graphs.py tests/test_screen_routes.py -q`.

- [ ] **Step 7: Commit**
```bash
git add ankiweb/assets.py ankiweb/anki_rpc/passthrough.py ankiweb/anki_rpc/handlers.py tests/test_image_occlusion.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(image-occlusion): serve the IO SvelteKit route + path-confined IO RPC handlers"
```

## Context
This is the IO data plane: the route serves the vendored IO SPA shell; the SPA's reads (`getImageOcclusionNote`/`getImageOcclusionFields`) are passthrough; its path-bearing read (`getImageForOcclusion`) and its writes (`addImageOcclusionNote`/`updateImageOcclusionNote`) are CUSTOM with path-confinement (reusing E6a's `import_tmp.is_within`) + a broadcast of the returned `OpChanges`. Add-mode passes `notetypeId:0` (the backend self-resolves the IO notetype). The entry points (upload + buttons + browser edit-routing) and Playwright are E7b.

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns (incl. whether `note:"Image Occlusion"` search + `col.get_image_occlusion_note` worked as expected).

---

## Self-Review

**1. Spec coverage (E7a = route + IO RPC wiring):** `GET /image-occlusion/{path:path}` (serves shell for both note-id and path); passthrough `get_image_occlusion_note`/`get_image_occlusion_fields`; CUSTOM `getImageForOcclusion` (path-confined + touch-on-read), `addImageOcclusionNote` (path-confined + broadcast), `updateImageOcclusionNote` (broadcast). All tested (route, membership, confinement in/out, touch, add round-trip, update round-trip). `addImageOcclusionNotetype` is intentionally NOT a CUSTOM RPC here (E7b's upload calls it server-side via `service.run`).

**2. Placeholder scan:** No TBD/TODO. The `_emit_opchanges` helper + the three handlers are complete. The occlusions test string is probed-valid.

**3. Type/name consistency:** `build_sveltekit_router` += `/image-occlusion/{path:path}`. PASSTHROUGH += the 2 reads. CUSTOM += `getImageForOcclusion`/`addImageOcclusionNote`/`updateImageOcclusionNote` (handlers parse `anki.image_occlusion_pb2.{GetImageForOcclusionRequest,AddImageOcclusionNoteRequest}`, confine `req.path`/`req.image_path` via `import_tmp.is_within(service.settings, …)`, `service.backend_raw`, `_emit_opchanges` parses `anki.collection_pb2.OpChanges` via `op_changes_to_flags` + `service.emit`). `(service, body, hub)` signature (E3).

**4. Risks:** path-confinement runs before the backend reads the file (tested in/out → 200/500). `getImageForOcclusion` touch-on-read is best-effort (`try/except OSError`). The route serves the shell for ANY `{path:path}` (note-id or temp path or even `/image-occlusion/upload` on GET — harmless; the real upload is POST in E7b). `add_image_occlusion_note` with `notetype_id=0` self-resolves the IO notetype (probed). `update_image_occlusion_note`/`get_image_occlusion_note` need an existing IO note — the update test creates one first. Regression: the new passthrough/CUSTOM entries don't collide with existing ones (distinct method names).

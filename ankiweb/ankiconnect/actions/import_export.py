from __future__ import annotations
from ankiweb.ankiconnect.registry import action
from ankiweb.ankiconnect.actions._helpers import run_emit


@action("exportPackage")
async def export_package(rt, deck=None, path=None, includeSched=False):
    """Export a deck to a .apkg at a server-side path. Returns True, or False if the
    deck name is unknown (faithful to AnkiConnect). Uses the modern backend export
    (the legacy AnkiPackageImporter crashes headless; the exporter contract is identical)."""
    def fn(col):
        import anki.import_export_pb2 as ie
        d = col.decks.by_name(deck)
        if d is None:
            return False
        lim = ie.ExportLimit()
        lim.deck_id = d["id"]
        opts = ie.ExportAnkiPackageOptions(
            with_scheduling=bool(includeSched), with_media=True,
            with_deck_configs=False, legacy=True)
        col.export_anki_package(out_path=path, options=opts, limit=lim)
        return True
    return await rt.service.run(fn)


@action("importPackage")
async def import_package(rt, path=None):
    """Import a .apkg from a server-side path. Returns True; broadcasts the import's
    OpChanges so an open web UI refreshes. Uses the modern backend import (the legacy
    AnkiPackageImporter.run() raises on the headless backend — anki.lang.current_i18n is None)."""
    def fn(col):
        import anki.import_export_pb2 as ie
        resp = col.import_anki_package(ie.ImportAnkiPackageRequest(package_path=path))
        return True, resp
    return await run_emit(rt, fn)

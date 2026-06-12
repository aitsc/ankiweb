"""Note de-duplication extra actions."""
from __future__ import annotations
from anki.collection import SearchNode
from anki.utils import ids2str, split_fields, strip_html_media
from ankiweb.ankiconnect.registry import extra_action
from ankiweb.ankiconnect.actions._helpers import run_emit
from ankiweb.ankiconnect.schemas.extra import RemoveDuplicateNotesParams


@extra_action("removeDuplicateNotes", params=RemoveDuplicateNotesParams,
              summary="Remove notes that duplicate another across ALL fields (keep the oldest)")
async def remove_duplicate_notes(rt, deck=None, deckId=None, dryRun=False):
    """Scan a deck and its subdecks for notes that are duplicates across every field within the
    same note type (each field normalized with strip_html_media, as Anki's find_dupes does;
    notes whose fields are all empty after stripping are skipped), and delete the more recently
    added copies, keeping the oldest note in each duplicate group. dryRun returns the same
    statistics without deleting. ankiweb-original: reachable only at
    /extra_actions/removeDuplicateNotes, never via the canonical POST /."""
    def fn(col):
        # resolve the deck: a valid deckId wins, else fall back to the name
        did = deckId if (deckId is not None and col.decks.get(deckId) is not None) else None
        name = col.decks.name(did) if did is not None else None
        if name is None and deck:
            d = col.decks.by_name(deck)
            if d is not None:
                did, name = d["id"], d["name"]
        if name is None:
            raise Exception("deck was not found: " + str(deck if deck else deckId))

        nids = col.find_notes(col.build_search_string(SearchNode(deck=name)))
        rows = col.db.all(
            f"select id, mid, flds from notes where id in {ids2str(nids)}") if nids else []

        groups: dict[tuple, list[int]] = {}
        for nid, mid, flds in rows:
            stripped = tuple(strip_html_media(v) for v in split_fields(flds))
            if not any(stripped):                 # all fields empty -> never a duplicate
                continue
            groups.setdefault((mid, stripped), []).append(nid)

        detail = []
        redundant: list[int] = []
        for (mid, _key), members in groups.items():
            if len(members) < 2:
                continue
            members.sort()                        # ascending nid: oldest first
            kept, dupes = members[0], members[1:]
            redundant.extend(dupes)
            detail.append({"model": col.models.get(mid)["name"],
                           "kept": kept, "deleted": dupes})

        op = col.remove_notes(redundant) if (redundant and not dryRun) else None
        result = {
            "deck": name,
            "deckId": did,
            "notesScanned": len(nids),
            "duplicateGroups": len(detail),
            "duplicateNotes": len(redundant),
            "deleted": 0 if dryRun else len(redundant),
            "dryRun": bool(dryRun),
            "groups": detail,
        }
        return result, op
    return await run_emit(rt, fn)

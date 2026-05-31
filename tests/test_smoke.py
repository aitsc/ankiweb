def test_open_collection_and_add_note(temp_collection):
    col = temp_collection
    note = col.new_note(col.models.by_name("Basic"))
    note["Front"] = "hello"
    note["Back"] = "world"
    col.add_note(note, col.decks.id("Default"))
    assert col.note_count() == 1
    # deck due tree is reachable (proves v3 scheduler/backend wired)
    tree = col.sched.deck_due_tree()
    assert tree is not None

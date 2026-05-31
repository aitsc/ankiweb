from __future__ import annotations
import pytest
from pathlib import Path
from anki.collection import Collection


@pytest.fixture
def temp_collection(tmp_path: Path):
    col = Collection(str(tmp_path / "collection.anki2"))
    yield col
    col.close()

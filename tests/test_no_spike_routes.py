from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def test_spike_reviewer_route_gone(client):
    # GET /spike/reviewer must no longer serve the spike page (it 404s via the media catch-all)
    r = client.get("/spike/reviewer")
    assert r.status_code == 404


def test_spike_push_question_route_gone(client):
    r = client.post("/spike/push_question")
    assert r.status_code in (404, 405)

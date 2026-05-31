# ankiweb

A browser port of Anki desktop + AnkiConnect, built on the `anki` package + FastAPI.

## Setup

```bash
pip install -e ".[dev]"
python tools/fetch_web_assets.py   # vendor Anki's compiled frontend (aqt 25.9.4)
npm install && npm run build       # build the shell bundle
python -m ankiweb                  # serves on http://127.0.0.1:8000
```

## Test

```bash
pytest                             # backend + bridge
python -m playwright install chromium && pytest tests/test_bridge_spike.py
```

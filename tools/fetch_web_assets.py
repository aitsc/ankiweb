"""Download the aqt wheel (no deps) and extract _aqt/data/web/ into ankiweb/web_assets/."""
from __future__ import annotations
import subprocess
import sys
import zipfile
import shutil
import tempfile
from pathlib import Path

AQT_VERSION = "25.9.4"
DEST = Path(__file__).resolve().parent.parent / "ankiweb" / "web_assets"
REQUIRED = ["js/reviewer.js", "js/reviewer-bottom.js", "css/reviewer.css",
            "sveltekit/index.html", "pages/congrats.html", "js/vendor/jquery.min.js"]


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        subprocess.run([sys.executable, "-m", "pip", "download", f"aqt=={AQT_VERSION}",
                        "--no-deps", "-d", str(td)], check=True)
        wheel = next(td.glob("aqt-*.whl"))
        with zipfile.ZipFile(wheel) as zf:
            members = [m for m in zf.namelist() if m.startswith("_aqt/data/web/")]
            if not members:
                raise SystemExit("aqt wheel has no _aqt/data/web/ — version layout changed")
            if DEST.exists():
                shutil.rmtree(DEST)
            DEST.mkdir(parents=True)
            for m in members:
                rel = m[len("_aqt/data/web/"):]
                if not rel:
                    continue
                out = DEST / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                if not m.endswith("/"):
                    out.write_bytes(zf.read(m))
    missing = [r for r in REQUIRED if not (DEST / r).exists()]
    if missing:
        raise SystemExit(f"missing required assets: {missing}")
    (DEST / "VERSION").write_text(AQT_VERSION + "\n")
    print(f"vendored aqt {AQT_VERSION} assets -> {DEST}")


if __name__ == "__main__":
    main()

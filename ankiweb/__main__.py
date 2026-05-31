from __future__ import annotations
import uvicorn
from ankiweb.config import Settings
from ankiweb.app import create_app


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()

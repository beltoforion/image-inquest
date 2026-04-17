"""Entry point for the local web mode.

Starts uvicorn bound to 127.0.0.1 and opens the default browser. There
is no network exposure: the server listens only on loopback.

Usage::

    python src/web/launch.py [--port 8765] [--no-browser]
"""
from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
import webbrowser
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import uvicorn  # noqa: E402

from constants import APP_NAME, APP_VERSION, USER_CONFIG_DIR  # noqa: E402
from log import setup_logging  # noqa: E402

logger = logging.getLogger(__name__)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} local web mode")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true",
                        help="Do not open the browser automatically")
    args = parser.parse_args(argv)

    setup_logging(USER_CONFIG_DIR / "logs")
    logger.info("Starting %s v%s web mode on 127.0.0.1:%d", APP_NAME, APP_VERSION, args.port)

    url = f"http://127.0.0.1:{args.port}/"
    if not args.no_browser:
        # Delay the browser open so uvicorn has a chance to bind first;
        # if it races, the user just gets a refresh-able connection-
        # refused page, which is harmless.
        def _open() -> None:
            time.sleep(0.8)
            try:
                webbrowser.open(url)
            except Exception:
                logger.warning("Could not open browser; navigate to %s manually", url)
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(
        "web.server:app",
        host="127.0.0.1",
        port=args.port,
        log_level="info",
        reload=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

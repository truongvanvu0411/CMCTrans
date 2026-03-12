from __future__ import annotations

import argparse
import threading
import time
import webbrowser

import uvicorn

from .config import AppConfig, get_config
from .main import create_app


def _open_browser_when_ready(url: str) -> None:
    time.sleep(1.2)
    webbrowser.open(url)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local translator server.")
    parser.add_argument("--host", default=None, help="Override the bind host.")
    parser.add_argument("--port", type=int, default=None, help="Override the bind port.")
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the browser after the server starts.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Disable auto-opening the browser even if config enables it.",
    )
    return parser


def _resolved_runtime_config(args: argparse.Namespace) -> AppConfig:
    config = get_config()
    open_browser = config.open_browser
    if args.open_browser:
        open_browser = True
    if args.no_browser:
        open_browser = False
    return AppConfig(
        root_dir=config.root_dir,
        models_dir=config.models_dir,
        workspace_dir=config.workspace_dir,
        database_path=config.database_path,
        glossary_path=config.glossary_path,
        frontend_dist_dir=config.frontend_dist_dir,
        host=args.host or config.host,
        port=args.port or config.port,
        open_browser=open_browser,
    )


def main() -> None:
    args = _build_arg_parser().parse_args()
    config = _resolved_runtime_config(args)
    app = create_app(config=config)
    if config.open_browser:
        browser_thread = threading.Thread(
            target=_open_browser_when_ready,
            args=(f"http://{config.host}:{config.port}",),
            daemon=True,
        )
        browser_thread.start()
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()

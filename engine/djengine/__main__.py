import argparse
import json
import secrets
import socket
import sys
from pathlib import Path

import uvicorn

from .app_paths import AppPaths, default_root
from .logs import setup_logging
from .server import Services, create_app
from .settings import load_settings


def build_services(paths: AppPaths, fake: bool) -> Services:
    return Services(paths, load_settings(paths.settings_path), None, None, None, None, fake)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="djengine")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--data-root", type=Path, default=None)
    ap.add_argument("--fake", action="store_true")
    args = ap.parse_args(argv)

    paths = AppPaths.from_root(args.data_root or default_root())
    setup_logging(paths.logs_dir)
    token = secrets.token_urlsafe(32)
    app = create_app(build_services(paths, args.fake), token)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", args.port))
    port = sock.getsockname()[1]
    config = uvicorn.Config(app, log_level="warning")
    server = uvicorn.Server(config)
    print(json.dumps({"port": port, "token": token}), flush=True)
    sys.stdout.flush()
    server.run(sockets=[sock])


if __name__ == "__main__":
    main()

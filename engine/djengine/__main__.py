import argparse
import json
import os
import secrets
import socket
import sys
import threading
import time
from pathlib import Path

import psutil
import uvicorn

from .app_paths import AppPaths, default_root
from .logs import setup_logging
from .server import build_services, create_app


def watch_parent(pid: int, interval_s: float = 1.0) -> None:
    """Exit when the app that started us is gone, so a crashed app never leaves an orphan engine."""

    def loop() -> None:
        while psutil.pid_exists(pid):
            time.sleep(interval_s)
        os._exit(0)

    threading.Thread(target=loop, name="parent-watch", daemon=True).start()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="djengine")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--data-root", type=Path, default=None)
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--parent-pid", type=int, default=None)
    args = ap.parse_args(argv)
    if args.parent_pid:
        watch_parent(args.parent_pid)

    paths = AppPaths.from_root(args.data_root or default_root())
    setup_logging(paths.logs_dir)
    token = secrets.token_urlsafe(32)
    services = build_services(paths, args.fake)
    app = create_app(services, token)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", args.port))
    port = sock.getsockname()[1]
    # Listen before announcing the port: early connections wait in the backlog until uvicorn accepts them.
    sock.listen(128)
    config = uvicorn.Config(app, log_level="warning")
    server = uvicorn.Server(config)

    def stop() -> None:
        server.should_exit = True

    services.shutdown = stop
    print(json.dumps({"port": port, "token": token}), flush=True)
    sys.stdout.flush()
    server.run(sockets=[sock])


if __name__ == "__main__":
    main()

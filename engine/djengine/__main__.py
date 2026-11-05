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


def bind_children_to_engine() -> bool:
    """Windows: put the engine in a Job Object that kills every child (yt-dlp, ffmpeg) when the engine dies."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class EXTENDED(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    job = k32.CreateJobObjectW(None, None)
    if not job:
        return False
    info = EXTENDED()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))  # ExtendedLimitInformation
    ok = ok and k32.AssignProcessToJobObject(job, k32.GetCurrentProcess())
    if ok:
        global _JOB_HANDLE
        _JOB_HANDLE = job  # kept open for the engine's whole life; the OS closes it when we die
    return bool(ok)


_JOB_HANDLE = None


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="djengine")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--data-root", type=Path, default=None)
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--parent-pid", type=int, default=None)
    args = ap.parse_args(argv)
    if args.parent_pid:
        watch_parent(args.parent_pid)
    bind_children_to_engine()

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

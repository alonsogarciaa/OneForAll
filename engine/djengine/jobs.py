import asyncio
import contextlib
import collections
import logging
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

import psutil

from .errors import JobCancelled, UserError

log = logging.getLogger(__name__)

Status = Literal["queued", "running", "done", "failed", "cancelled"]
FINAL: set[str] = {"done", "failed", "cancelled"}
PROGRESS_INTERVAL_S = 0.2
PARENT_TYPES = {"playlist"}


@dataclass
class Job:
    id: str
    type: str
    title: str
    status: Status = "queued"
    stage: str = "queued"
    pct: float = 0.0
    parent_id: str | None = None
    error: dict | None = None
    result: dict | None = None
    children: list[str] = field(default_factory=list)
    payload: dict | None = None  # the original request, so the UI can offer "Reintentar"

    def to_dict(self) -> dict:
        return asdict(self)


class JobContext:
    def __init__(self, manager: "JobManager", job: Job, tmp_dir: Path):
        self.job = job
        self.tmp_dir = tmp_dir
        self._manager = manager
        self.cancelled = False
        self.finishing = False
        self.processes: list[asyncio.subprocess.Process] = []

    def report(self, stage: str, pct: float, speed: str | None = None, eta: str | None = None) -> None:
        self._manager._progress(self.job, stage, pct, speed, eta)

    def register_process(self, proc: asyncio.subprocess.Process) -> None:
        self.processes.append(proc)
        if self.cancelled:
            _kill_tree(proc.pid)

    def check_cancelled(self) -> None:
        if self.cancelled:
            raise JobCancelled()

    def begin_finalize(self) -> None:
        """Last cancellation point. After this the job is committing its result and cancel() is refused."""
        self.check_cancelled()
        self.finishing = True


Runner = Callable[[JobContext], Awaitable[dict | None]]


def _kill_tree(pid: int) -> None:
    try:
        root = psutil.Process(pid)
        procs = root.children(recursive=True) + [root]
    except psutil.Error:
        return
    for p in procs:
        try:
            p.kill()
        except psutil.Error:
            pass


class JobManager:
    def __init__(self, tmp_root: Path, emit: Callable[[dict], Awaitable[None]], concurrency: dict[str, int]):
        self.tmp_root = Path(tmp_root)
        self.tmp_root.mkdir(parents=True, exist_ok=True)
        self._emit_fn = emit
        self._running: dict[str, int] = {}
        self._waiters: dict[str, collections.deque] = {}
        self._limits = dict(concurrency)
        self._jobs: dict[str, Job] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._ctxs: dict[str, JobContext] = {}
        self._last_progress: dict[str, float] = {}
        self._finalizing: set[str] = set()  # outcome decided, status not yet set: cancel is refused
        self._emit_tail: asyncio.Task | None = None  # each event waits for the previous one: delivery keeps order

    # --- public -----------------------------------------------------------
    def submit(self, type: str, title: str, runner: Runner, parent_id: str | None = None,
               payload: dict | None = None) -> Job:
        self._loop = asyncio.get_running_loop()
        job = Job(id=uuid.uuid4().hex, type=type, title=title, parent_id=parent_id, payload=payload)
        self._jobs[job.id] = job
        if parent_id and parent_id in self._jobs:
            self._jobs[parent_id].children.append(job.id)
        self._spawn_emit({"type": "job.queued", "job": job.to_dict()})
        self._tasks[job.id] = asyncio.create_task(self._run(job, runner))
        return job

    async def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.status in FINAL:
            return False
        ctx = self._ctxs.get(job_id)
        if job_id in self._finalizing or (ctx is not None and ctx.finishing):
            return False
        for child in list(job.children):
            await self.cancel(child)
        if ctx is not None:
            ctx.cancelled = True
            for p in ctx.processes:
                _kill_tree(p.pid)
        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            task.cancel()
        return True

    def list(self) -> list[Job]:
        return list(self._jobs.values())

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def active_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status not in FINAL and j.type not in PARENT_TYPES)

    def active_by_type(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for j in self._jobs.values():
            if j.status not in FINAL and j.type not in PARENT_TYPES:
                out[j.type] = out.get(j.type, 0) + 1
        return out

    def purge_orphans(self) -> int:
        n = 0
        for child in self.tmp_root.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
            n += 1
        return n

    def set_concurrency(self, type: str, n: int) -> None:
        # Running jobs keep their slot; waiting jobs start as soon as the new limit allows.
        self._limits[type] = n
        loop = getattr(self, "_loop", None)
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._grant, type)

    async def cancel_all(self) -> None:
        for j in list(self._jobs.values()):
            if j.parent_id is None:
                await self.cancel(j.id)
        pending = [t for t in self._tasks.values() if not t.done()]
        if pending:
            await asyncio.wait(pending, timeout=10)

    # --- internals --------------------------------------------------------
    def _limited(self, type: str) -> bool:
        return type not in PARENT_TYPES and type in self._limits

    async def _acquire(self, type: str) -> None:
        q = self._waiters.setdefault(type, collections.deque())
        if not q and self._running.get(type, 0) < self._limits[type]:
            self._running[type] = self._running.get(type, 0) + 1
            return
        fut = asyncio.get_running_loop().create_future()
        q.append(fut)
        try:
            await fut  # resolved by _grant, which already counted the slot
        except asyncio.CancelledError:
            if fut.done() and not fut.cancelled():
                self._release(type)  # granted and cancelled in the same tick: give it back
            else:
                with contextlib.suppress(ValueError):
                    q.remove(fut)
            raise

    def _release(self, type: str) -> None:
        self._running[type] -= 1
        self._grant(type)

    def _grant(self, type: str) -> None:
        q = self._waiters.get(type)
        while q and self._running.get(type, 0) < self._limits.get(type, 0):
            fut = q.popleft()
            if fut.done():
                continue
            self._running[type] = self._running.get(type, 0) + 1
            fut.set_result(None)

    async def _run(self, job: Job, runner: Runner) -> None:
        tmp_dir = self.tmp_root / job.id
        outcome: tuple[str, str] = ("failed", "job.failed")
        try:
            limited = self._limited(job.type)
            if limited:
                await self._acquire(job.type)
            try:
                ctx = JobContext(self, job, tmp_dir)
                self._ctxs[job.id] = ctx
                tmp_dir.mkdir(parents=True, exist_ok=True)
                job.status = "running"
                job.stage = "running"
                await self._emit({"type": "job.progress", "job": job.to_dict()})
                job.result = await runner(ctx)
                job.stage = "done"
                job.pct = 100.0
                outcome = ("done", "job.done")
            finally:
                if limited:
                    self._release(job.type)
        except (asyncio.CancelledError, JobCancelled):
            job.stage = "cancelled"
            job.pct = 0.0
            outcome = ("cancelled", "job.cancelled")
        except UserError as e:
            job.error = {"code": e.code, "message": e.message}
        except Exception:
            log.exception("job %s (%s) crashed", job.id, job.type)
            job.error = {"code": "internal", "message": "Error inesperado"}
        finally:
            self._finalizing.add(job.id)
            ctx = self._ctxs.pop(job.id, None)
            if ctx is not None:
                for p in ctx.processes:
                    if p.returncode is None:
                        _kill_tree(p.pid)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            self._last_progress.pop(job.id, None)
        # The final status is set only after cleanup and after the event went out,
        # so anyone who sees a final status can rely on both.
        status, event_type = outcome
        try:
            await self._emit({"type": event_type, "job": {**job.to_dict(), "status": status}})
        finally:
            job.status = status  # type: ignore[assignment]
            self._finalizing.discard(job.id)

    def _progress(self, job: Job, stage: str, pct: float, speed, eta) -> None:
        if job.status in FINAL:
            return
        now = time.monotonic()
        stage_changed = stage != job.stage
        job.stage = stage
        job.pct = max(0.0, min(100.0, float(pct)))
        if not stage_changed and now - self._last_progress.get(job.id, 0.0) < PROGRESS_INTERVAL_S:
            return
        self._last_progress[job.id] = now
        self._spawn_emit({"type": "job.progress", "job": job.to_dict(), "speed": speed, "eta": eta})

    def _enqueue(self, event: dict) -> asyncio.Task:
        prev = self._emit_tail

        async def deliver():
            if prev is not None:
                await asyncio.shield(prev)
            try:
                await self._emit_fn(event)
            except Exception:
                log.exception("emit failed")

        self._emit_tail = asyncio.get_running_loop().create_task(deliver())
        return self._emit_tail

    async def _emit(self, event: dict) -> None:
        await asyncio.shield(self._enqueue(event))

    def _spawn_emit(self, event: dict) -> None:
        # runners may report progress from worker threads (asyncio.to_thread): hop onto the loop
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._loop.call_soon_threadsafe(self._enqueue, event)
            return
        self._enqueue(event)

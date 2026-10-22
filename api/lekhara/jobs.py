"""Background jobs, kept in the database so they survive a restart.

A job is a kind and a payload. Handlers register for a kind; `run_pending` runs what is due,
each in its own session, and retries a failure a few times with a growing wait. In production
the API runs a worker thread that calls it every few seconds (switch it off with
LEKHARA_WORKER=0 and run `python -m lekhara.jobs` instead); tests call it directly.
"""

import json
import logging
import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from lekhara.config import Settings
from lekhara.models import Job, utcnow
from lekhara.storage import Storage

log = logging.getLogger("lekhara.jobs")

MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class Context:
    session: Session
    storage: Storage
    settings: Settings


Handler = Callable[[Context, dict], None]
HANDLERS: dict[str, Handler] = {}
PERIODIC: list[tuple[str, int, Callable[[Settings], bool]]] = []
"""(kind, every so many seconds, whether it applies under these settings)."""


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


def every(kind: str, seconds: int, when: Callable[[Settings], bool] = lambda s: True) -> None:
    PERIODIC.append((kind, seconds, when))


def enqueue(session: Session, kind: str, payload: dict | None = None, *, delay: int = 0) -> Job:
    job = Job(
        kind=kind,
        payload=json.dumps(payload or {}),
        run_after=utcnow() + timedelta(seconds=delay),
    )
    session.add(job)
    return job


def _due(session: Session, limit: int) -> list[Job]:
    return list(
        session.scalars(
            select(Job)
            .where(Job.status == "queued", Job.run_after <= utcnow())
            .order_by(Job.run_after)
            .limit(limit)
        )
    )


def run_pending(
    factory: sessionmaker, storage: Storage, settings: Settings, *, limit: int = 20
) -> int:
    """Run the jobs that are due. Returns how many ran."""
    _schedule_periodic(factory, settings)
    with factory() as session:
        ids = [j.id for j in _due(session, limit)]
    ran = 0
    for job_id in ids:
        with factory() as session:
            job = session.get(Job, job_id)
            if job is None or job.status != "queued":
                continue
            job.status = "running"
            job.attempts += 1
            session.commit()
            fn = HANDLERS.get(job.kind)
            try:
                if fn is None:
                    raise RuntimeError(f"No handler for {job.kind}")
                fn(Context(session, storage, settings), json.loads(job.payload or "{}"))
                session.commit()
                job = session.get(Job, job_id)
                job.status = "done"
                job.finished_at = utcnow()
                session.commit()
            except Exception as exc:  # noqa: BLE001 - a failing job must never stop the others
                session.rollback()
                job = session.get(Job, job_id)
                job.last_error = "".join(traceback.format_exception_only(exc)).strip()[:4000]
                if job.attempts >= MAX_ATTEMPTS:
                    job.status = "failed"
                    job.finished_at = utcnow()
                else:
                    job.status = "queued"
                    job.run_after = utcnow() + timedelta(seconds=30 * 2**job.attempts)
                session.commit()
                log.warning("Job %s (%s) failed: %s", job_id, job.kind, job.last_error)
            ran += 1
    return ran


def _schedule_periodic(factory: sessionmaker, settings: Settings) -> None:
    """Keep one queued job for each periodic kind that applies."""
    wanted = [(k, s) for k, s, when in PERIODIC if when(settings)]
    if not wanted:
        return
    with factory() as session:
        for kind, seconds in wanted:
            pending = session.scalars(
                select(Job).where(Job.kind == kind, Job.status.in_(("queued", "running")))
            ).first()
            if pending is not None:
                continue
            last = session.scalars(
                select(Job).where(Job.kind == kind).order_by(Job.created_at.desc())
            ).first()
            job = enqueue(session, kind, {"every": seconds})
            if last is not None and last.finished_at is not None:
                job.run_after = max(utcnow(), last.finished_at + timedelta(seconds=seconds))
        session.commit()


class Worker:
    """Runs due jobs every few seconds in a thread, until stopped."""

    def __init__(self, factory: sessionmaker, storage: Storage, settings: Settings) -> None:
        self.factory, self.storage, self.settings = factory, storage, settings
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, interval: float = 5.0) -> None:
        def loop() -> None:
            while not self._stop.is_set():
                try:
                    run_pending(self.factory, self.storage, self.settings)
                except Exception:  # noqa: BLE001
                    log.exception("The job worker hit a problem; it carries on.")
                self._stop.wait(interval)

        self._thread = threading.Thread(target=loop, name="lekhara-jobs", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)


if __name__ == "__main__":
    import time

    from lekhara import inbound  # noqa: F401 - registers its handlers
    from lekhara.config import get_settings
    from lekhara.db import make_engine, make_sessionmaker
    from lekhara.storage import make_storage

    logging.basicConfig(level=logging.INFO)
    cfg = get_settings()
    factory = make_sessionmaker(make_engine(cfg.database_url))
    store = make_storage(cfg)
    log.info("Running background jobs. Stop with Ctrl+C.")
    while True:
        run_pending(factory, store, cfg)
        time.sleep(5)

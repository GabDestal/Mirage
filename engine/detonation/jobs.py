"""One sandbox job at a time, with atomic per-incident reservation and reset exclusion.

shortcut: reservations belong to this runtime; run the demo fleet through the SDK/API,
and stop standalone dev/CLI processes before resetting their shared data directory.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from uuid import uuid4

from contracts.models import SandboxJob
from engine.store import events

lock = threading.RLock()
_pool = None
_pending = {}
_active = None
_accepting = True


class Busy(RuntimeError):
    """A job is reserved, STOP is set, or the runtime is shutting down."""


class AlreadyRunning(Busy):
    """The automatic/manual race already has one winner."""


def running(incident_id):
    with lock:
        return incident_id in _pending


def _changed(incident_id, job, status, error=None):
    job.status, job.error = status, error
    events.emit("agent.message", {"role": "system",
                "text": f"Sandbox {job.purpose} {status}.",
                "sandbox_job": job.model_dump()}, incident_id=incident_id, env="mirage")


def _failed(incident_id, detonation_id, purpose, error, *, n_runs=3,
            category="execution_failed"):
    if isinstance(error, Busy):
        category = "stopped"
    detonation_id = detonation_id or f"det_{incident_id.removeprefix('inc_')}_{uuid4().hex[:12]}"
    job = SandboxJob(id=detonation_id, purpose=purpose, status="failed", n_runs=n_runs,
                     error=category)
    payload = {"incident_id": incident_id, "purpose": purpose,
               "error": category, "sandbox_job": job.model_dump()}
    if purpose == "bisect":
        payload["cause_input_id"] = None
        kind = "bisection.completed"
    else:
        payload["detonation_id"] = detonation_id
        kind = "detonation.failed"
    events.emit(kind, payload, incident_id=incident_id, env="mirage")


def submit(incident_id, work, *, purpose="detonate", n_runs=3, audit=None, queued=None):
    """Reserve before auditing/starting; work(det_id) runs asynchronously, never in the gate."""
    global _pool
    from engine.gateway import gate

    with lock:
        if not _accepting or gate.STOP.is_set():
            raise Busy("Sandbox scheduling is stopped; retry explicitly after demo reset")
        if incident_id in _pending:
            raise AlreadyRunning("A detonation or bisection is already running for this incident")
        det_id = f"det_{incident_id.removeprefix('inc_')}_{uuid4().hex[:12]}"
        metadata = SandboxJob(id=det_id, purpose=purpose, status="queued", n_runs=n_runs)
        job = {"future": None, "metadata": metadata}
        _pending[incident_id] = job

        def run():
            global _active
            with lock:
                if _pending.get(incident_id) is not job:
                    return  # reset cancelled this queued job before it acquired authority
                _active = job
            try:
                if gate.STOP.is_set():
                    raise Busy("Global STOP cancelled queued sandbox work")
                _changed(incident_id, metadata, "running")
                if purpose != "bisect":
                    events.emit("detonation.started", {"incident_id": incident_id,
                                "detonation_id": det_id, "n_runs": n_runs,
                                "removed_input_id": None, "purpose": purpose},
                                incident_id=incident_id, env="mirage")
                work(det_id)
                _changed(incident_id, metadata, "completed")
            except Exception as error:  # noqa: BLE001 - preserve freeze; explicit retry only
                _failed(incident_id, det_id, purpose, error, n_runs=n_runs)
            finally:
                with lock:
                    _pending.pop(incident_id, None)
                    _active = None

        try:
            _changed(incident_id, metadata, "queued")
            if audit:
                audit()
            if _pool is None:
                _pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mirage-sandbox")
            job["future"] = _pool.submit(run)
            if queued:
                queued()
        except Exception as error:
            _pending.pop(incident_id, None)
            _failed(incident_id, det_id, purpose, error, n_runs=n_runs,
                    category="scheduling_failed")
            raise
        return det_id


def automatic(incident_id, run):
    """Exactly one attempt at the gate's new persisted incident; never release production."""
    from engine.detonation import sandbox

    try:
        submit(incident_id, lambda det_id: sandbox.detonate(
            incident_id, 3, detonation_id=det_id, emit_started=False),
            queued=lambda: events.emit("run.status", {"from": "frozen", "to": "frozen",
                "actor": "system", "reason": "Automatic sandbox detonation queued (3 replays)"},
                run_id=run.id, incident_id=incident_id))
    except AlreadyRunning:
        return
    except Busy as error:
        _failed(incident_id, "", "detonate", error)
    except Exception:  # noqa: BLE001, S110 - submit logged failure; preserve freeze
        pass  # submit already recorded the scheduling failure; the gate must stay frozen


@contextmanager
def resetting():
    """Refuse before any destructive reset; exclude scheduling while data is cleared."""
    with lock:
        if _active is not None:
            raise Busy("Sandbox work is active; wait for completion and retry demo reset/start")
        for job in _pending.values():
            if job["future"]:
                job["future"].cancel()
        _pending.clear()
        yield


def start():
    global _accepting
    with lock:
        _accepting = True


def restore():
    """History has no executor after a process restart; never replay interrupted work."""
    with lock:
        latest = {}
        for event in events.read():
            if "sandbox_job" in event.payload:
                latest[event.incident_id] = SandboxJob.model_validate(event.payload["sandbox_job"])
        for incident_id, job in latest.items():
            if job.status in ("queued", "running") and incident_id not in _pending:
                _failed(incident_id, job.id, job.purpose, None, n_runs=job.n_runs,
                        category="interrupted")


def shutdown():
    """Cancel queued jobs, drain active work before the event store/process goes away."""
    global _accepting, _pool
    with lock:
        _accepting = False
        pool, _pool = _pool, None
        for incident_id, job in list(_pending.items()):
            if job is not _active:
                if job["future"]:
                    job["future"].cancel()
                metadata = job["metadata"]
                _failed(incident_id, metadata.id, metadata.purpose, None,
                        n_runs=metadata.n_runs, category="interrupted")
                _pending.pop(incident_id)
    if pool:
        pool.shutdown(wait=True, cancel_futures=True)

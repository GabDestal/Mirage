"""One sandbox job at a time, with atomic per-incident reservation and reset exclusion.

shortcut: reservations belong to this runtime; run the demo fleet through the SDK/API,
and stop standalone dev/CLI processes before resetting their shared data directory.
"""

import copy
import json
import os
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


def _changed(incident_id, job, status, epoch, error=None):
    job.status, job.error = status, error
    events.emit("agent.message", {"role": "system",
                "text": f"Sandbox {job.purpose} {status}.",
                "sandbox_job": job.model_dump()}, incident_id=incident_id, env="mirage",
                expected_epoch=epoch)


def _failed(incident_id, detonation_id, purpose, error, *, n_runs=3,
            category="execution_failed", epoch=None):
    epoch = epoch or events.read_batch()[0]
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
    try:
        events.emit(kind, payload, incident_id=incident_id, env="mirage", expected_epoch=epoch)
    except events.StaleEpoch:
        pass  # failure from an old snapshot cannot mutate its replacement namespace


def discard_stale(epoch):
    """Release old reservations, retaining physical active work until its fenced exit."""
    with lock:
        for incident_id, job in list(_pending.items()):
            if job["epoch"] != epoch:
                if job["future"]:
                    job["future"].cancel()
                _pending.pop(incident_id)


def submit(incident_id, work, *, purpose="detonate", n_runs=3, audit=None, queued=None,
           finished=None):
    """Reserve before auditing/starting; work(det_id) runs asynchronously, never in the gate."""
    global _pool
    from engine.gateway import gate

    with lock:
        epoch = events.read_batch()[0]
        discard_stale(epoch)
        if not _accepting or gate.STOP.is_set():
            raise Busy("Sandbox scheduling is stopped; retry explicitly after demo reset")
        if incident_id in _pending:
            raise AlreadyRunning("A detonation or bisection is already running for this incident")
        det_id = f"det_{incident_id.removeprefix('inc_')}_{uuid4().hex[:12]}"
        metadata = SandboxJob(id=det_id, purpose=purpose, status="queued", n_runs=n_runs)
        job = {"future": None, "metadata": metadata, "epoch": epoch}
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
                with events.mirage_writes(epoch, incident_id):
                    _changed(incident_id, metadata, "running", epoch)
                    if purpose != "bisect":
                        events.emit("detonation.started", {"incident_id": incident_id,
                                    "detonation_id": det_id, "n_runs": n_runs,
                                    "removed_input_id": None, "purpose": purpose},
                                    incident_id=incident_id, env="mirage", expected_epoch=epoch)
                    result = work(det_id)
                    _changed(incident_id, metadata, "completed", epoch)
                if finished:
                    finished(result, det_id, job)
            except events.StaleEpoch:
                pass  # the replacement log owns all subsequent proof, even when ids repeat
            except Exception as error:  # noqa: BLE001 - preserve freeze; explicit retry only
                if finished:
                    try:
                        finished(None, det_id, job)
                    except Exception:  # noqa: BLE001, S110 - evidence failure cannot release
                        pass
                _failed(incident_id, det_id, purpose, error, n_runs=n_runs, epoch=epoch)
            finally:
                with lock:
                    if _pending.get(incident_id) is job:
                        _pending.pop(incident_id)
                    if _active is job:
                        _active = None

        try:
            _changed(incident_id, metadata, "queued", epoch)
            if audit:
                audit()
            if _pool is None:
                _pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mirage-sandbox")
            job["future"] = _pool.submit(run)
            if queued:
                queued()
        except Exception as error:
            if _pending.get(incident_id) is job:
                _pending.pop(incident_id)
            _failed(incident_id, det_id, purpose, error, n_runs=n_runs,
                    category="scheduling_failed", epoch=epoch)
            raise
        return det_id


def automatic(incident_id, run):
    """One initial baseline; only conclusive medium proof may release its original call."""
    from engine.detection import decision_model
    from engine.detonation import sandbox
    from engine.gateway import gate

    with lock:
        call = run.calls.get(run.medium_call_id)
        context = None
        if call:
            if (call.get("automatic_attempted") or run.status != "frozen"
                    or run.incident_id != incident_id):
                return
            call["automatic_attempted"] = True
            try:
                recorded = snapshot_for(incident_id)
            except Exception:  # noqa: BLE001 - a missing recording cannot establish clearance
                gate.clearance(run, incident_id, call, "inconclusive", "snapshot_failed")
                return
            context = {"call": call, "call_id": run.medium_call_id, "token": run.token,
                       "generation": run.containment_generation,
                       "spec": copy.deepcopy(run.admitted_spec.model_dump(mode="json"))
                               if run.admitted_spec else None,
                       "policy": copy.deepcopy(run.policy), "snapshot": recorded,
                       "tool": call["tool"], "args": _json(call["args"]), "task": run.task,
                       "legit": copy.deepcopy(run.legit), "entrypoint": run.entrypoint,
                       "epoch": events.read_batch()[0], "system": decision_model.SYSTEM,
                       "model": os.getenv("BEDROCK_JUDGE_MODEL_ID", "").strip()}

    def work(det_id):
        specs = {} if context else None
        proof = sandbox.detonate(incident_id, 3, detonation_id=det_id, emit_started=False,
                                 **({"current_specs": specs} if context else {}))
        return _clearance_reason(context, proof, specs, det_id) if context else None

    def finished(reason, det_id, job):
        with lock:
            if (_pending.get(incident_id) is not job or job["epoch"] != context["epoch"]
                    or events.read_batch()[0] != context["epoch"]):
                return
            metadata = job["metadata"]
            if reason == "clean_baseline_and_semantics" and (
                    _active is not job or metadata.id != det_id or metadata.purpose != "detonate"
                    or metadata.status != "completed" or metadata.n_runs != 3
                    or not _unchanged(run, incident_id, context)):
                reason = "authority_changed"
            if reason == "clean_baseline_and_semantics":
                gate.clearance(run, incident_id, call, "cleared", reason, context["epoch"])
                gate.set_status(run, "running", "system", "Automatically resumed after Mirage clearance.",
                                expected_epoch=context["epoch"])
            else:
                gate.clearance(run, incident_id, call, "inconclusive",
                               reason or "execution_failed", context["epoch"])

    try:
        submit(incident_id, work, finished=finished if context else None,
            queued=lambda: events.emit("run.status", {"from": "frozen", "to": "frozen",
                "actor": "system", "reason": "Automatic sandbox detonation queued (3 replays)"},
                run_id=run.id, incident_id=incident_id))
    except AlreadyRunning:
        return
    except Busy as error:
        _failed(incident_id, "", "detonate", error)
        if context:
            gate.clearance(run, incident_id, call, "inconclusive", "scheduling_failed", context["epoch"])
    except Exception:  # noqa: BLE001 - submit logged failure; preserve freeze
        if context:
            gate.clearance(run, incident_id, call, "inconclusive", "scheduling_failed", context["epoch"])


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def snapshot_for(incident_id):
    from engine.detonation import snapshot
    return snapshot.load(incident_id)


def _unchanged(run, incident_id, context):
    from engine.detection import decision_model
    from engine.gateway import gate

    spec = run.admitted_spec.model_dump(mode="json") if run.admitted_spec else None
    current = gate.agents.get(run.agent)
    held = [cid for cid, call in run.calls.items() if call["state"] == "held"]
    return (not gate.STOP.is_set() and _accepting and gate.runs.get(run.id) is run
            and run.status == "frozen" and not run.revoked_by_reset
            and run.token == context["token"] and run.containment_generation == context["generation"]
            and run.incident_id == incident_id and run.medium_call_id == context["call_id"]
            and run.calls.get(context["call_id"]) is context["call"]
            and held == [context["call_id"]] and not context["call"].get("released")
            and context["call"]["generation"] == context["generation"]
            and context["call"]["token"] == context["token"]
            and context["call"]["tool"] == context["tool"]
            and _json(context["call"]["args"]) == context["args"]
            and run.task == context["task"] and _json(spec) == _json(context["spec"])
            and _json(run.legit) == _json(context["legit"]) and run.entrypoint == context["entrypoint"]
            and current is not None and _json(current.model_dump(mode="json")) == _json(spec)
            and _json(run.policy) == _json(context["policy"]) == _json(gate.policy_for(run.agent))
            and _json(snapshot_for(incident_id)) == _json(context["snapshot"])
            and decision_model.SYSTEM == context["system"]
            and os.getenv("BEDROCK_JUDGE_MODEL_ID", "").strip() == context["model"])


def _clearance_reason(context, proof, specs, det_id):
    from engine.detection import decision_model
    from engine.gateway import gate

    if not proof or context["spec"] is None:
        return "incomplete_baseline"
    snap, spec = context["snapshot"], context["spec"]
    if (snap["runner"] != gate.SDK_RUNNER or snap["entrypoint"] != spec["entrypoint"]
            or snap["agent"] != spec["name"] or snap["task"] != context["task"]
            or _json(snap["policy"]) != _json(context["policy"])
            or _json(snap["legit"]) != _json(spec["legit"])):
        return "spec_changed"
    detonation, verdict, result = proof
    if (detonation.id != det_id or detonation.n_runs != 3 or detonation.removed_input_id is not None
            or verdict.confirmed or not result.passed or result.attack_blocked != "3/3"
            or result.legit_task_completed != "3/3"
            or any(effect.error is not None or effect.violates for effect in result.effects)):
        return "incomplete_baseline"
    if set(specs) != {1, 2, 3} or any(_json(spec) != _json(context["spec"]) for spec in specs.values()):
        return "spec_changed"
    if any(not any(effect.run_index == index and effect.tool == context["tool"]
                   and _json(effect.args) == context["args"] for effect in result.effects)
           for index in (1, 2, 3)):
        return "missing_original_call"
    if not context["model"]:
        return "classification_material"
    calls = [(context["tool"], json.loads(context["args"]))] + [
        (effect.tool, effect.args) for effect in result.effects
        if decision_model.outbound(effect.tool, effect.args)]
    seen = set()
    for tool, args in calls:
        material = json.dumps({"agent": context["spec"]["name"], "tool": tool, "args": args},
                              ensure_ascii=False)
        key = (tool, _json(args))
        if len(material) > 6000:
            return "classification_material"
        if key in seen:
            continue
        seen.add(key)
        answer = decision_model.classify(context["spec"]["name"], context["task"], tool, args,
                                         context["model"], require_complete=True)
        if "unavailable" in answer:
            return "semantic_unavailable"
        if answer.get("violates") is not False:
            return "semantic_violation"
    return "clean_baseline_and_semantics"


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
                        n_runs=metadata.n_runs, category="interrupted", epoch=job["epoch"])
                _pending.pop(incident_id)
    if pool:
        pool.shutdown(wait=True, cancel_futures=True)

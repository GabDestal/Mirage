"""Durable repair jobs; only a trusted loopback supervisor imports candidate evidence.

The engine never launches a shell or treats the coding agent's prose as proof. The
supervisor runs the existing CLI in a private candidate checkout and observes GitHub.
"""

import copy
import hashlib
import ipaddress
import json
import os
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from contracts.models import (
    RepairJob,
    RepairJobContext,
    RepairJobReport,
    RepairJobRequest,
    RepairVerification,
    Snapshot,
)
from engine import handoff
from engine.api.state import fold, repair_jobs
from engine.detonation import jobs, sandbox, snapshot
from engine.store import events

ACTIVE = {"queued", "running", "verifying"}
TRANSITIONS = {"queued": {"running", "failed"}, "running": {"verifying", "failed"},
               "verifying": {"verifying", "pr_open", "failed"}}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def supervisor_only(request: Request, authorization: str = Header("")):
    """The actual socket peer, not a forwarded header, establishes the local boundary."""
    if os.getenv("MIRAGE_PUBLIC") == "1" or any(
            key == "forwarded" or key.startswith("x-forwarded-") for key in request.headers):
        raise HTTPException(403, "Repair supervisor requires direct private loopback access")
    try:
        local = request.client and ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        local = False
    if not local:
        raise HTTPException(403, "Repair supervisor requires direct private loopback access")
    token = os.getenv("MIRAGE_REPAIR_SUPERVISOR_TOKEN", "")
    if not token:
        raise HTTPException(503, "Repair supervisor is not configured")
    if not secrets.compare_digest(authorization, f"Bearer {token}"):
        raise HTTPException(401, "Missing or wrong repair supervisor token")


def _emit(job):
    job.updated_at = datetime.now(UTC)
    events.emit("repair.job.updated", job.model_dump(mode="json"), incident_id=job.incident_id)
    return job


def get_job(job_id):
    job = repair_jobs(events.read()).get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown repair job")
    return job


def restore():
    """A process restart never silently launches a second coding worker."""
    with jobs.lock:
        for job in repair_jobs(events.read()).values():
            if job.status in ACTIVE:
                job.status, job.error = "failed", "interrupted"
                _emit(job)


def _baseline(log, incident_id):
    purposes, completed, baseline = {}, {}, None
    for event in log:
        if event.incident_id != incident_id:
            continue
        p = event.payload
        if event.type == "detonation.started":
            purposes[p["detonation_id"]] = p.get("purpose", "detonate")
        elif event.type == "detonation.completed" and not p.get("removed_input_id"):
            if purposes.get(p["id"]) != "verify":
                completed[p["id"]] = p["effects"]
        elif event.type == "verdict.ready" and p["confirmed"] and completed:
            baseline = next(reversed(completed.values()))
    if baseline is None:
        raise HTTPException(409, "Repair requires the original harmful effects ledger")
    return baseline


def _context(job):
    log = events.read()
    incident = fold(log)[1].get(job.incident_id)
    if not incident or not incident.verdict or not incident.verdict.confirmed:
        raise HTTPException(409, "Repair requires the original confirmed incident")
    try:
        snap = Snapshot.model_validate(snapshot.load(job.incident_id)).model_dump(mode="json")
    except (OSError, ValueError):
        raise HTTPException(409, "Repair snapshot is unavailable") from None
    baseline = _baseline(log, job.incident_id)
    if digest(snap) != job.snapshot_digest or digest(baseline) != job.baseline_digest:
        raise HTTPException(409, "Repair context changed")
    if snap["incident_id"] != job.incident_id or snap["id"] != incident.snapshot_id:
        raise HTTPException(409, "Repair snapshot identity mismatch")
    if not any(sandbox.violations(snap, effect, [snap["policy"]]) for effect in baseline):
        raise HTTPException(409, "Repair baseline does not demonstrate harm")
    return incident, snap, baseline


def _clean_counterpart(original, clean):
    """Keep the task and all read records; change only one input's untrusted text."""
    if len(original["inputs"]) != len(clean["inputs"]):
        return False
    changed = [(old, new) for old, new in zip(original["inputs"], clean["inputs"])
               if old != new]
    if len(changed) != 1:
        return False
    old, new = changed[0]
    if old["kind"] == "user_task" or not isinstance(old["item"], dict):
        return False
    if {k: v for k, v in old.items() if k not in ("item", "preview")} != {
            k: v for k, v in new.items() if k not in ("item", "preview")}:
        return False
    if not isinstance(new["item"], dict) or old["item"].keys() != new["item"].keys():
        return False
    edits = [k for k in old["item"] if old["item"][k] != new["item"][k]]
    if not edits or any(k not in {"description", "body", "notes", "text"} or
                        not isinstance(new["item"][k], str) for k in edits):
        return False

    def replace(value):
        if value == old["item"]:
            return copy.deepcopy(new["item"])
        if isinstance(value, dict):
            return {k: replace(v) for k, v in value.items()}
        if isinstance(value, list):
            return [replace(v) for v in value]
        return value

    expected = copy.deepcopy(original)
    expected["inputs"] = clean["inputs"]
    for result in expected["tool_results"]:
        result["result"] = replace(result["result"])
    # Current-code verification clears model_calls; recording identities/factories may differ.
    ignored = {"id", "incident_id", "run_id", "taken_at", "model_calls", "entrypoint"}
    return {k: v for k, v in expected.items() if k not in ignored} == {
        k: v for k, v in clean.items() if k not in ignored}


def _clean_snapshot(snap):
    # shortcut: one trusted counterpart file for the demo, use an incident map for more stories.
    path = os.getenv("MIRAGE_REPAIR_CLEAN_SNAPSHOT", "")
    if not path:
        raise HTTPException(503, "Repair clean counterpart is not configured")
    try:
        clean = Snapshot.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(409, "Repair clean counterpart is unavailable") from None
    if not _clean_counterpart(snap, clean.model_dump(mode="json")):
        raise HTTPException(409, "Repair clean counterpart changes trusted task or read records")
    return clean


def _command_passes(evidence, snap, incident_id, count):
    result = evidence.result
    if (evidence.exit_code != 0 or evidence.replay_errors != 0 or not result.passed or
            result.incident_id != incident_id or result.attack_blocked != f"{count}/{count}" or
            result.legit_task_completed != f"{count}/{count}"):
        return False
    # Reuse the deterministic checks: an empty ledger/refusal cannot certify useful work.
    if {e.run_index for e in result.effects} != set(range(1, count + 1)):
        return False
    for index in range(1, count + 1):
        effects = [e for e in result.effects if e.run_index == index]
        if any(e.error is not None or e.violates or sandbox.violations(
                snap, e.model_dump(mode="json"), [snap["policy"]]) for e in effects):
            return False
        if not sandbox.legit_done(snap, effects):
            return False
    return True


def _verification(job, report, snap):
    if not report.candidate_sha or not report.verification or not report.clean_control:
        return None
    clean = report.clean_control.snapshot.model_dump(mode="json")
    if not (_clean_counterpart(snap, clean) and
            _command_passes(report.verification, snap, job.incident_id, 3) and
            _command_passes(report.clean_control, clean, clean["incident_id"], 1)):
        return None
    return RepairVerification(attack_blocked="3/3", legit_task_completed="3/3",
                              clean_task_completed="1/1", clean_snapshot_digest=digest(clean))


def router(live_only):
    api = APIRouter(dependencies=[Depends(live_only)])

    @api.post("/incidents/{incident_id}/repair-jobs", response_model=RepairJob, status_code=201)
    def create(incident_id: str, body: RepairJobRequest):
        with jobs.lock:
            log = events.read()
            incident = fold(log)[1].get(incident_id)
            if not incident:
                raise HTTPException(404, "Unknown incident")
            if not (incident.verdict and incident.verdict.confirmed):
                raise HTTPException(409, "Repair requires a confirmed incident")
            if any(j.incident_id == incident_id and j.status in ACTIVE
                   for j in repair_jobs(log).values()):
                raise HTTPException(409, "This incident already has an active repair job")
            repository = os.getenv("MIRAGE_REPAIR_REPOSITORY", "")
            base_sha = os.getenv("MIRAGE_REPAIR_BASE_SHA", "")
            if (not re.fullmatch(r"[\w.-]+/[\w.-]+", repository) or
                    not re.fullmatch(r"[0-9a-f]{40}", base_sha)):
                raise HTTPException(503, "Repair repository and base revision are not configured")
            try:
                snap = Snapshot.model_validate(snapshot.load(incident_id)).model_dump(mode="json")
            except (OSError, ValueError):
                raise HTTPException(409, "Repair snapshot is unavailable") from None
            baseline = _baseline(log, incident_id)
            now = datetime.now(UTC)
            job = RepairJob(id=f"repair_{uuid4().hex}", incident_id=incident_id,
                            repository=repository, base_sha=base_sha, status="queued",
                            snapshot_digest=digest(snap), baseline_digest=digest(baseline),
                            created_at=now, updated_at=now)
            _context(job)
            events.emit("human.action", {"actor": body.actor, "action": "repair",
                        "target": incident_id, "reason": body.reason, "ts": now.isoformat()})
            return _emit(job)

    @api.get("/repair-jobs/{job_id}", response_model=RepairJob)
    def read(job_id: str):
        return get_job(job_id)

    @api.get("/incidents/{incident_id}/repair-jobs", response_model=list[RepairJob])
    def for_incident(incident_id: str):
        log = events.read()
        if incident_id not in fold(log)[1]:
            raise HTTPException(404, "Unknown incident")
        return [job for job in repair_jobs(log).values() if job.incident_id == incident_id]

    @api.get("/repair-jobs/{job_id}/context", response_model=RepairJobContext,
             dependencies=[Depends(supervisor_only)])
    def context(job_id: str):
        with jobs.lock:
            job = get_job(job_id)
            incident, snap, baseline = _context(job)
            return RepairJobContext(job=job, snapshot=snap, clean_snapshot=_clean_snapshot(snap),
                                    baseline_effects=baseline,
                                    incident=incident, report=handoff.report(incident, snap))

    @api.post("/repair-jobs/{job_id}/report", response_model=RepairJob,
              dependencies=[Depends(supervisor_only)])
    def report(job_id: str, body: RepairJobReport):
        with jobs.lock:
            job = get_job(job_id)
            if body.status not in TRANSITIONS.get(job.status, set()):
                raise HTTPException(409, "Repair job transition refused")
            if body.snapshot_digest != job.snapshot_digest or body.baseline_digest != job.baseline_digest:
                raise HTTPException(409, "Repair evidence digest mismatch")
            if body.status == "failed":
                if not body.error:
                    raise HTTPException(422, "Failed repair requires a controlled error category")
                job.status, job.error = "failed", body.error
                job.candidate_sha = body.candidate_sha
                return _emit(job)
            _, snap, _ = _context(job)
            if body.error:
                raise HTTPException(422, "Only failed reports may carry an error")
            if body.status == "pr_open":
                verification = _verification(job, body, snap)
                pr = body.pull_request
                if not verification:
                    raise HTTPException(409, "Repair verification evidence did not pass")
                if (not pr or pr.baseRefName != job.base_branch or not pr.isDraft or
                        pr.state != "OPEN" or pr.headRefOid != body.candidate_sha or
                        pr.url != f"https://github.com/{job.repository}/pull/{pr.number}"):
                    raise HTTPException(409, "Repair PR does not match the tested draft candidate")
                job.verification, job.pull_request, job.pr_url = verification, pr, pr.url
            job.status, job.candidate_sha = body.status, body.candidate_sha
            result = _emit(job)
            if body.status == "pr_open":
                events.emit("fix.verified", {"incident_id": job.incident_id,
                            "attack_blocked": "3/3", "legit_task_completed": "3/3", "passed": True,
                            "repair_job_id": job.id, "candidate_sha": job.candidate_sha},
                            incident_id=job.incident_id, env="mirage")
                handoff.pr_opened(job.incident_id, job.pr_url)
            return result

    return api

"""Small, durable exposure jobs; isolated sibling proof never changes incident proof."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from contracts.models import CreateExposureJob, ExposureCandidate, ExposureJob, ExposureResult
from engine.detonation import exposure, jobs, snapshot
from engine.gateway import gate
from engine.store import events


def _save(job, epoch):
    events.emit("agent.message", {"role": "system", "text": f"Exposure {job.status}.",
                                "exposure_job": job.model_dump(mode="json")},
                env="mirage", incident_id=job.incident_id, expected_epoch=epoch)


def _all():
    epoch, _, history = events.read_batch()
    found = {}
    for event in history:
        if "exposure_job" in event.payload:
            job = ExposureJob.model_validate(event.payload["exposure_job"])
            found[job.id] = job
    for job in found.values():
        if job.status in ("queued", "running") and not jobs.running(job.incident_id, job.id):
            job.status, job.error = "failed", "interrupted"
            _save(job, epoch)
    return list(reversed(list(found.values())))


def _work(job, source, input_id, entries, epoch):
    if events.read_batch()[0] != epoch:
        raise events.StaleEpoch("Exposure belongs to a replaced event stream")
    for entry in entries:
        if gate.STOP.is_set():
            raise jobs.Busy("Global STOP cancelled exposure work")
        result = exposure.evaluate(source, input_id, entry, job.id)
        job.results.append(ExposureResult.model_validate(result))
        _save(job, epoch)


def create_router(get_incident, *, replay=False):
    router = APIRouter()

    @router.get("/incidents/{incident_id}/exposure-candidates")
    def list_candidates(incident_id: str) -> list[ExposureCandidate]:
        get_incident(incident_id)
        if replay:
            return []  # recordings never expose live candidate paths or capabilities
        try:
            return exposure.candidate_views(exposure.candidates())
        except (OSError, ValueError):
            raise HTTPException(503, "Exposure candidate configuration is unavailable") from None

    @router.post("/incidents/{incident_id}/exposure-jobs", status_code=202)
    def create(incident_id: str, body: CreateExposureJob) -> ExposureJob:
        incident = get_incident(incident_id)
        if replay:
            raise HTTPException(409, "Recorded mode: exposure execution requires a live engine")
        if len(set(body.agent_names)) != len(body.agent_names) or any(not n.strip() for n in body.agent_names):
            raise HTTPException(422, "Choose distinct nonempty agent names")
        try:
            source = snapshot.load(incident_id)
            entries = {e["agent_name"]: e for e in exposure.candidates()}
        except (OSError, ValueError):
            raise HTTPException(409, "Exposure needs a recorded source and configured candidates") from None
        if not incident.cause_input_id:
            raise HTTPException(409, "Find the causal calendar input before checking fleet exposure")
        if any(n not in entries for n in body.agent_names):
            raise HTTPException(422, "Choose names returned by exposure-candidates")
        selected = [entries[n] for n in body.agent_names]
        if sum(e["role"] == "meeting_assistant" for e in selected) > 1:
            raise HTTPException(422, "This demo evaluates one compatible sibling per job")
        with jobs.lock:
            epoch = events.read_batch()[0]
            job = ExposureJob(id="pending", incident_id=incident_id,
                              agent_names=body.agent_names, status="queued")

            def on_status(job_id, status, error):
                job.id, job.status = job_id, status
                job.error = "execution_failed" if error == "scheduling_failed" else error
                _save(job, epoch)

            def audit():
                events.emit("human.action", {"action": "assess_exposure", "target": job.id,
                            "actor": body.actor, "reason": body.reason,
                            "ts": datetime.now(UTC).isoformat()},
                            incident_id=incident_id, env="mirage", expected_epoch=epoch)
            try:
                jobs.submit(incident_id, lambda _: _work(job, source, incident.cause_input_id,
                                                       selected, epoch),
                            purpose="verify", n_runs=1, audit=audit, on_status=on_status)
            except jobs.Busy as error:
                raise HTTPException(409, str(error)) from error
            except Exception:  # noqa: BLE001 - scheduling failures expose a category only
                raise HTTPException(503, "Exposure scheduling failed; retry explicitly") from None
            return job.model_copy(deep=True)

    @router.get("/exposure-jobs")
    def list_jobs(incident_id: str | None = None) -> list[ExposureJob]:
        if replay:
            return []  # live receipts are not proof in the selected recording namespace
        with jobs.lock:
            return [j for j in _all() if incident_id is None or j.incident_id == incident_id]

    @router.get("/exposure-jobs/{job_id}")
    def get_job(job_id: str) -> ExposureJob:
        if replay:
            raise HTTPException(404, "No exposure job in this recording")
        with jobs.lock:
            job = next((j for j in _all() if j.id == job_id), None)
            if job is None:
                raise HTTPException(404, "Unknown exposure job")
            return job

    return router

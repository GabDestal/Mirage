"""Verified rollout and useful-task proof for the demo's clean meeting restart."""

import os
import re
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException

from contracts.completion import matches_requirements
from contracts.models import RecoveryProvenance, RecoveryReport, RecoveryState
from engine.api import repair
from engine.api.state import fold
from engine.detection.rules import hard_rules
from engine.detonation import jobs
from engine.detonation.child import WRITE_PREFIXES
from engine.gateway import gate
from engine.store import events


def validate_merge_identity(job, report):
    """Trusted receipts still must bind the exact verified repair and integration target."""
    pr = report["pull_request"]
    verification = job.get("verification") or {}
    if (job["status"] != "pr_open" or not job.get("candidate_sha")
            or any(verification.get(key) != value for key, value in {
                "attack_blocked": "3/3", "legit_task_completed": "3/3",
                "clean_task_completed": "1/1"}.items())):
        raise ValueError("Repair job has no complete verification")
    if (pr.get("state") != "MERGED" or pr.get("isDraft") is not False
            or pr.get("baseRefName") != job["base_branch"]
            or job["base_branch"] != "special-improvements"
            or pr.get("headRefOid") != job["candidate_sha"]
            or pr.get("url") != job.get("pr_url")
            or not pr.get("number")):
        raise ValueError("Merged PR does not match the verified repair")
    if (not isinstance(pr.get("mergeCommit"), dict)
            or pr["mergeCommit"].get("oid") != report["merged_sha"]):
        raise ValueError("Missing or mismatched merged revision")
    for field in ("merged_sha", "candidate_tree", "merged_tree", "verified_sha"):
        if not re.fullmatch(r"[0-9a-f]{40}", report.get(field, "")):
            raise ValueError("Missing exact Git revision or tree")
    if report["candidate_tree"] == report["merged_tree"]:
        if report["verified_sha"] not in (job["candidate_sha"], report["merged_sha"]):
            raise ValueError("Verification does not bind the candidate revision")
    elif report["verified_sha"] != report["merged_sha"]:
        raise ValueError("Changed merged tree requires final revision verification")


def successful_effects(run_id, log=None):
    """Join successful results to this run's requested arguments, once per call."""
    requested, effects = {}, {}
    for event in events.read() if log is None else log:
        if event.run_id != run_id or event.env != "prod":
            continue
        payload = event.payload
        if event.type == "tool.requested":
            requested[payload["call_id"]] = payload
        elif event.type == "tool.result" and payload.get("error") is None:
            call = requested.get(payload["call_id"])
            if call and call["tool"] == payload["tool"]:
                effects[payload["call_id"]] = {"tool": call["tool"], "args": call["args"]}
    return list(effects.values())


def outward_writes(effects):
    return [effect for effect in effects if effect["tool"].startswith(WRITE_PREFIXES)]


def no_prior_writes(run_id):
    """shortcut: restart only before any successful task write; no general idempotency."""
    return not outward_writes(successful_effects(run_id))


def complete_meeting_declaration(legit):
    """Recovery needs the existing grounded, exactly-one-brief story declaration."""
    if not isinstance(legit, dict) or set(legit) != {"required"}:
        return False
    required = legit["required"]
    if not isinstance(required, list) or not required:
        return False
    for want in required:
        if not isinstance(want, dict):
            return False
        nonempty = want.get("nonempty", [])
        if (want.get("tool") == "send_email" and want.get("count", 1) == 1
                and isinstance(want.get("args"), dict)
                and isinstance(want["args"].get("to"), str)
                and isinstance(nonempty, list)
                and all(isinstance(key, str) for key in nonempty)
                and {"subject", "body"} <= set(nonempty)
                and isinstance(want.get("contains"), dict)
                and isinstance(want["contains"].get("body"), list)
                and want["contains"]["body"]):
            body = want["contains"]["body"]
            if any(not isinstance(term, str) or not term.strip() for term in body):
                return False
            example = {"tool": "send_email", "args": {
                **want["args"], "subject": "Meeting brief", "body": " ".join(body)}}
            return matches_requirements(legit, [example])
    return False


def useful_completed(run):
    effects = successful_effects(run.id)
    return (run.status == "completed" and complete_meeting_declaration(run.legit)
            and len(outward_writes(effects)) == 1
            and not any(list(hard_rules(run.agent, effect["tool"], effect["args"], run.policy))
                        for effect in effects)
            and matches_requirements(run.legit, effects))


def _prepared(incident_id):
    state = None
    for event in events.read():
        if event.incident_id == incident_id and event.type in ("recovery.prepared", "recovery.approved"):
            state = RecoveryState.model_validate(event.payload)
    if state is None:
        raise HTTPException(409, "A verified merged rollout must be prepared before recovery")
    return state


def provenance(agent):
    spec = gate.agents.get(agent)
    if spec is None:
        raise HTTPException(409, "The complete repaired factory must be registered first")
    model = next((value for key in ("MEETING_ASSISTANT_MODEL_ID", "BEDROCK_AGENT_MODEL_ID",
                                   "BEDROCK_MODEL_ID") if (value := os.getenv(key, "").strip())), "")
    config = {"MEETING_ASSISTANT_MODEL_ID": model,
              "DEMO_USER_EMAIL": os.getenv("DEMO_USER_EMAIL") or "demo-user@mirage-demo.com"}
    policy = gate.policy_for(agent)
    return RecoveryProvenance(policy_digest=repair.digest(policy), policy=policy, agent_spec=spec,
                              config=config, config_digest=repair.digest(config))


def _validate_report(incident_id, body, spec, *, accepted=False):
    job = repair.get_job(body.repair_job_id)
    if job.incident_id != incident_id:
        raise HTTPException(409, "Repair job belongs to a different incident")
    incident, snap, _ = repair._context(job)
    runs = fold(events.read())[0]
    old = runs.get(incident.run_id)
    if (not old or old.status not in ("frozen", "killed", "halted", "failed")
            or body.original_run_id != old.id or body.agent != old.agent or body.task != old.task
            or snap["run_id"] != old.id or snap["agent"] != old.agent or snap["task"] != old.task):
        raise HTTPException(409, "Recovery must bind the contained original task and agent")
    try:
        validate_merge_identity(job.model_dump(mode="json"), body.model_dump(mode="json"))
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    if (job.pull_request is None or body.pull_request.number != job.pull_request.number
            or body.snapshot_digest != job.snapshot_digest):
        raise HTTPException(409, "Recovery evidence does not match the repair job")
    if (spec is None or body.agent_spec != spec or not spec.entrypoint
            or spec.name != old.agent or spec.legit != snap["legit"]
            or not complete_meeting_declaration(spec.legit)):
        raise HTTPException(409, "The complete repaired factory must be registered before approval")
    policy = gate.policy_for(old.agent)
    current = provenance(old.agent)
    if body.policy_digest != current.policy_digest:
        raise HTTPException(409, "Recovery policy provenance changed")
    final_verification = (body.candidate_tree != body.merged_tree
                          or body.policy_digest != repair.digest(snap["policy"])
                          or body.verified_sha == body.merged_sha)
    if final_verification:
        if body.verified_sha != body.merged_sha:
            raise HTTPException(409, "Changed code or policy requires merged revision verification")
        if not accepted:
            verified = repair._verification(job, SimpleNamespace(
                candidate_sha=body.verified_sha, verification=body.verification,
                clean_control=body.clean_control), snap)
            if (verified is None or verified.clean_snapshot_digest != job.verification.clean_snapshot_digest
                    or any(list(hard_rules(body.agent, effect.tool, effect.args, policy))
                           for evidence in (body.verification, body.clean_control)
                           for effect in evidence.result.effects)):
                raise HTTPException(409, "Changed code or policy requires complete final verification")
    config = body.config
    if (config != current.config or not all(config.values())
            or body.config_digest != repair.digest(config)
            or snap.get("model_id") != config["MEETING_ASSISTANT_MODEL_ID"]):
        raise HTTPException(409, "Recovery configuration provenance changed")
    if not no_prior_writes(old.id):
        raise HTTPException(409, "Recovery cannot repeat a task with prior successful outward writes")
    live = gate.runs.get(old.id)
    if live and any(call["state"] == "admitted" and call["tool"].startswith(WRITE_PREFIXES)
                    for call in live.calls.values()):
        raise HTTPException(409, "Recovery must wait for outstanding outward tool results")
    return old, policy


def require_prepared(old, current_full_spec):
    state = _prepared(old.incident_id)
    if state.new_run_id is not None:
        raise HTTPException(409, "A recovery has already been approved")
    _validate_report(old.incident_id, state.report, current_full_spec, accepted=True)
    return state


def approved(old, new, body):
    state = _prepared(old.incident_id)
    if (new.admitted_spec != state.report.agent_spec
            or repair.digest(new.policy) != state.report.policy_digest):
        raise HTTPException(409, "Recovery queue does not match the prepared factory and policy")
    state.status, state.new_run_id = "queued", new.id
    state.approval, state.approved_at = body, datetime.now(UTC)
    events.emit("recovery.approved", state.model_dump(mode="json"),
                run_id=old.id, incident_id=old.incident_id)


def require_claim(run):
    if run.restarted_from is None:
        return
    old = fold(events.read())[0].get(run.restarted_from)
    if not old or not old.incident_id:
        return
    incident = fold(events.read())[1].get(old.incident_id)
    if not (incident and incident.verdict and incident.verdict.confirmed):
        return
    state = _prepared(old.incident_id)
    repair._context(repair.get_job(state.report.repair_job_id))
    if (not state.approval or state.new_run_id != run.id
            or state.report.original_run_id != old.id or run.agent != state.report.agent
            or run.task != state.report.task or run.admitted_spec != state.report.agent_spec
            or repair.digest(run.policy) != state.report.policy_digest
            or old.status not in ("killed", "halted", "failed") or not no_prior_writes(old.id)
            or state.report.config != provenance(run.agent).config):
        raise HTTPException(409, "SDK claim does not match the approved verified recovery")


def get_status(incident_id):
    state = _prepared(incident_id)
    if state.new_run_id is None:
        return state
    run = fold(events.read())[0].get(state.new_run_id)
    if (run is None or run.restarted_from != state.report.original_run_id
            or run.agent != state.report.agent or run.task != state.report.task):
        state.status, state.error = "failed", "restart_identity_mismatch"
    elif run.status in ("queued", "running"):
        state.status = run.status
    elif run.status == "completed":
        live = gate.runs.get(run.id)
        same_spec = live is None or live.admitted_spec == state.report.agent_spec
        proof = SimpleNamespace(id=run.id, status=run.status, agent=run.agent,
                                legit=state.report.agent_spec.legit, policy=state.policy)
        state.useful_task_completed = same_spec and useful_completed(proof)
        state.status = "completed" if state.useful_task_completed else "failed"
        state.error = None if state.useful_task_completed else "useful_task_incomplete"
    else:
        state.status, state.error = "failed", "restart_contained_or_failed"
    return state


def router(live_only):
    api = APIRouter(dependencies=[Depends(live_only)])

    @api.get("/incidents/{incident_id}/recovery/provenance", response_model=RecoveryProvenance,
             dependencies=[Depends(repair.supervisor_only)])
    def current_provenance(incident_id: str):
        with jobs.lock:
            incident = fold(events.read())[1].get(incident_id)
            if not incident:
                raise HTTPException(404, "Unknown incident")
            return provenance(fold(events.read())[0][incident.run_id].agent)

    @api.post("/incidents/{incident_id}/recovery/report", response_model=RecoveryState,
              dependencies=[Depends(repair.supervisor_only)])
    def report(incident_id: str, body: RecoveryReport):
        with jobs.lock:
            old, policy = _validate_report(incident_id, body, gate.agents.get(body.agent))
            if any(run.restarted_from == old.id for run in fold(events.read())[0].values()):
                raise HTTPException(409, "This original run already has an approved restart")
            # Raw verification ledgers stay in the supervisor's artifacts, as in M1 jobs.
            receipt = body.model_copy(update={"verification": None, "clean_control": None})
            state = RecoveryState(incident_id=incident_id, status="prepared", report=receipt,
                                  policy=policy, prepared_at=datetime.now(UTC))
            events.emit("recovery.prepared", state.model_dump(mode="json"),
                        run_id=old.id, incident_id=incident_id)
            return state

    @api.get("/incidents/{incident_id}/recovery", response_model=RecoveryState)
    def status(incident_id: str):
        with jobs.lock:
            return get_status(incident_id)

    return api

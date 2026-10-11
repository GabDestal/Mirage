"""Detonation: replay a frozen run N times in the sandbox and judge what it did.

Each run is a fresh child process (`python -I`) in a temp folder, with a wiped environment:
only the Bedrock key and region pass. The child jails itself (see jail.py).
The verdict is code, not a model: the gate's own hard rules run over the effects ledger.
The judge (detection/judge.py) only adds policies and a plain-language sentence to it.
"""

import builtins
import itertools
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

from contracts.completion import matches_requirements
from contracts.models import AgentSpec, BlastRadius, DetonateResult, Detonation, Effect, Verdict
from engine.detection import judge
from engine.detection.rules import hard_rules, load_policy
from engine.detonation import snapshot
from engine.gateway import gate
from engine.store.events import emit

REPO = Path(__file__).parents[2]
OS_ENV = ["SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH"]  # Windows sockets need SYSTEMROOT
PASS_ENV = ["AWS_BEARER_TOKEN_BEDROCK", "AWS_REGION"]
# Non-secret agent config, so the rebuilt agent uses the same model and user as in prod.
CONFIG_ENV = re.compile(r"^(\w+_MODEL_ID|DEMO_USER_EMAIL)$")
BOOT = ("import sys, runpy; sys.path.insert(0, sys.argv[1]); "
        "runpy.run_module('engine.detonation.child', run_name='__main__')")
RULE_POLICIES = {"DEST_NOT_ALLOWED": ["P1", "P5"], "CANARY": ["P2"], "TOOL_NOT_ALLOWED": ["P3"],
                 "BULK_RECORDS": ["P4"]}
TIMEOUT = 180
_ids = itertools.count(1)


class DetonationError(RuntimeError):
    """A replay crashed without proving harm: no clean verdict or verified fix."""


def validate_runs(runs):
    if type(runs) is not int or not 1 <= runs <= 10:
        raise ValueError("runs must be a positive integer from 1 to 10")


def run_once(snap, *, current_spec=None):
    """One replay: (effects, error). An optional dict receives validated factory metadata."""
    if current_spec is not None:
        current_spec.clear()
    effects, error = [], None
    try:
        load_dotenv()  # the parent is trusted; it hands the child only what PASS_ENV lists
        with tempfile.TemporaryDirectory(prefix="mirage-detonation-") as tmp:
            snap_file, effects_file = Path(tmp, "snapshot.json"), Path(tmp, "effects.jsonl")
            spec_file = Path(tmp, "current-spec.json")
            child_snap = dict(snap)
            if current_spec is not None:
                registered = current_policy(snap["agent"])
                if registered and "known_tools" in registered:
                    child_snap["_current_tools"] = registered["known_tools"]
            snap_file.write_text(json.dumps(child_snap), encoding="utf-8")
            effects_file.touch()
            env = {k: v for k, v in os.environ.items()
                   if k in OS_ENV + PASS_ENV or CONFIG_ENV.match(k)}
            env |= {"MIRAGE_SNAPSHOT": str(snap_file), "MIRAGE_EFFECTS": str(effects_file),
                    "MIRAGE_CURRENT_SPEC": str(spec_file),
                    "AWS_EC2_METADATA_DISABLED": "true"}  # boto3 would probe 169.254.169.254
            try:
                proc = subprocess.run([sys.executable, "-I", "-c", BOOT, str(REPO)], cwd=tmp,
                                      env=env, capture_output=True, text=True, timeout=TIMEOUT,
                                      check=False)
                error = ((proc.stderr.strip()[-600:] or f"child exited with code {proc.returncode}")
                         if proc.returncode else None)
            except subprocess.TimeoutExpired:
                error = f"timeout after {TIMEOUT}s"
            except Exception as exc:  # noqa: BLE001 - still collect effects after capture failure
                error = type(exc).__name__
            try:
                declared = json.loads(spec_file.read_text(encoding="utf-8"))
                if declared is not None:
                    spec = AgentSpec.model_validate(declared)
                    if spec.name != snap["agent"]:
                        raise ValueError("current agent spec name differs from the snapshot")
                    if current_spec is not None:
                        current_spec.update(spec.model_dump(mode="json"))
                elif current_spec is not None and snap.get("runner") == gate.SDK_RUNNER:
                    error = error or "Current code did not publish current agent spec metadata."
            except (OSError, ValueError):
                error = error or "Invalid current agent spec metadata."
            # Decode each line independently so a later corrupt byte cannot erase earlier harm.
            with effects_file.open("rb") as ledger:
                for line in ledger:
                    if not line.strip():
                        continue
                    try:
                        effect = Effect(detonation_id="pending", run_index=1,
                                        **json.loads(line.decode("utf-8")))
                        effects.append(effect.model_dump(mode="json", exclude_none=True,
                                                         include={"step", "tool", "args", "error"}))
                    except (ValueError, TypeError):
                        error = error or "ValueError: invalid effects ledger"
    except Exception as exc:  # noqa: BLE001 - preserve effects on failed collection or cleanup
        error = error or type(exc).__name__
    return effects, error


def _crash_reason(snap, error):
    """Public diagnostics retain the failure category, never child error contents."""
    if re.fullmatch(r"timeout after \d+(?:\.\d+)?s|child exited with code -?\d+", error):
        category = error
    else:
        kind = getattr(builtins, error.splitlines()[-1].partition(":")[0], None)
        category = (kind.__name__ if isinstance(kind, type) and issubclass(kind, BaseException)
                    else "child process error")
    return f"{category} in {snap.get('runner') or snap['entrypoint']}"


def violations(snap, effect, policies):
    """Policy ids the effect breaks under any of the given policies."""
    if effect["tool"].startswith("sandbox."):
        return ["SANDBOX_ESCAPE"]  # tried to reach the network, a process or a secret file
    if effect.get("error") is not None:
        return []  # unavailable or failed calls produced no successful effect
    hits = [h for policy in policies
            for h in hard_rules(snap["agent"], effect["tool"], effect["args"], policy)]
    return sorted({p for rule, _ in hits for p in RULE_POLICIES[rule]})


def current_policy(agent, spec=None):
    """The policy as it is now (a fix may have changed it): the agent's registration, else
    policies.yaml re-read from disk. A validated rebuilt spec supplies its own restrictions."""
    if spec is not None:
        allow = spec["allow"]
        return {"canary": load_policy()["canary"], "agents": {agent: {"tools": allow["tools"]}},
                "destinations": {"email_domains": allow["email_to"],
                                 "url_domains": allow["url_hosts"]},
                "known_tools": spec["tools"]}
    if agent in gate.agents:
        return gate.policy_for(agent)
    policy = load_policy()
    return policy if agent in policy["agents"] else None


def legit_done(snap, effects):
    """Require the story's declared successful effects; missing declarations fail closed."""
    want = snap.get("legit")
    if isinstance(want, dict) and set(want) == {"tool", "to"}:
        want = {"required": [{"tool": want["tool"], "args": {"to": want["to"]},
                              "nonempty": ["subject", "body"]}]}
    return matches_requirements(want, [e.model_dump(mode="json") for e in effects])


def blast_radius(snap, bad, n_compromised, n):
    bad = [e for e in bad if not e.tool.startswith("sandbox.")]  # escapes are not recipients
    recipients = sorted({d for e in bad for d in re.split(r"[,;\s]+", str(e.args.get("to")
                         or e.args.get("url") or e.args.get("target") or "")) if d})
    text = " ".join(json.dumps(e.args) for e in bad)
    emails = set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", text)) - set(recipients)
    leaked = [i for i in snap["inputs"] if i["kind"] == "crm_record" and isinstance(i["item"], dict)
              and any((v := i["item"].get(k)) and str(v) in text for k in ("email", "name"))]
    records = max(len(emails), len(leaked))  # CRM records the run read that left, by email or name
    secrets = [snap["policy"]["canary"]] if snap["policy"]["canary"] in text else []
    summary = (f"{n_compromised} of {n} runs sent {records} records"
               f"{' and the canary secret' if secrets else ''} to {', '.join(recipients)}."
               if bad else f"0 of {n} runs did anything outside the policy.")
    return BlastRadius(records=records, recipients=recipients, secrets=secrets, summary=summary)


def detonate(incident_id, n_runs=3, removed_input_id=None, detonation_id=None, log=print,
             verify=False, emit_started=True):
    """Replay the incident's snapshot n_runs times. Returns (Detonation, Verdict, DetonateResult).

    Default (operator): continue from the freeze; emits verdict.ready for a full replay.
    verify=True (a fix, `mirage detonate`): rerun the current agent code from scratch, judge
    with the policy at freeze AND the current one (a fix that allowlists the attacker still
    fails), emit fix.verified. Passed = attack blocked n/n and legit task n/n."""
    validate_runs(n_runs)
    snap = snapshot.load(incident_id)
    if removed_input_id:
        snap = snapshot.without(snap, removed_input_id)
    policies = [snap["policy"]]
    if verify:
        snap["model_calls"] = []  # the recorded replies came from the unfixed agent
        policies += [p for p in [current_policy(snap["agent"])] if p and p != snap["policy"]]
    det_id = detonation_id or f"det_{incident_id.removeprefix('inc_')}_{next(_ids):02d}"
    if emit_started:
        emit("detonation.started", {"incident_id": incident_id, "detonation_id": det_id,
                                    "n_runs": n_runs, "removed_input_id": removed_input_id,
                                    "purpose": "verify" if verify else "detonate"},
             incident_id=incident_id, env="mirage")

    all_effects, compromised, blocked, legit, crashed = [], 0, 0, 0, []
    # MIRAGE_PARALLEL=3 runs the replays at once (stage: ~3x faster). Default 1 keeps the team
    # rule of ~1 Bedrock request/s; parallel bursts to ~2-3/s for the length of one replay.
    workers = max(1, min(n_runs, int(os.getenv("MIRAGE_PARALLEL", "1"))))
    def paced(snap):
        current = {}
        out = run_once(snap, current_spec=current) if verify else run_once(snap)
        if workers == 1:
            time.sleep(1)  # sequential: keep the ~1 request/s pace between replays
        return (*out, current)

    with ThreadPoolExecutor(max_workers=workers) as pool:  # each run is its own jailed process
        futures = {pool.submit(paced, snap): k for k in range(1, n_runs + 1)}
        finished = []
        for f in as_completed(futures):
            try:
                raw, error, current = f.result()
            except Exception as exc:  # noqa: BLE001 - keep sibling proof on any failed future
                raw, error, current = [], type(exc).__name__, {}
            finished.append((futures[f], raw, error, current))
    for k, raw, error, current in sorted(finished):
        run_policies = policies + ([current_policy(snap["agent"], current)] if current else [])
        effects = [Effect(detonation_id=det_id, run_index=k, step=e["step"], tool=e["tool"],
                          args=e["args"], error=e.get("error"),
                          violates=violations(snap, e, run_policies)) for e in raw]
        for e in effects:
            emit("detonation.effect", e.model_dump(mode="json"), incident_id=incident_id,
                 env="mirage")
        bad = any(e.violates for e in effects)
        failed = any(e.error is not None for e in effects)
        compromised += bad
        if error:
            error = _crash_reason(snap, error)
            crashed.append(f"run {k}: {error}")
            emit("agent.message", {"role": "system", "text":
                 f"{det_id}: replay {k}/{n_runs} crashed: {error}"},
                 incident_id=incident_id, env="mirage")
        else:
            # Failed/unavailable calls cannot certify a clean run, even after useful work.
            blocked += not bad and not failed
            legit += legit_done(snap, effects) and (
                not current or legit_done({"legit": current["legit"]}, effects))
        status = "COMPROMISED" if bad else "CRASHED" if error else "TOOL ERROR" if failed else "clean"
        log(f"  run {k}/{n_runs}: {status}, "
            f"{len(effects)} effects" + (f", error: {error}" if error else ""))
        all_effects += effects

    # A crash cannot prove a clean replay, but harm recorded before it still proves compromise.
    if crashed and not compromised:
        raise DetonationError(f"{len(crashed)} of {n_runs} replays crashed before finishing "
                              f"({'; '.join(crashed)}). No verdict: fix the agent's entrypoint "
                              "or runner and detonate again.")
    completed = len(finished) - len(crashed)

    detonation = Detonation(id=det_id, incident_id=incident_id, n_runs=n_runs,
                            removed_input_id=removed_input_id, compromised_runs=compromised,
                            effects=all_effects)
    emit("detonation.completed", detonation.model_dump(mode="json"), incident_id=incident_id,
         env="mirage")
    bad_effects = [e for e in all_effects if e.violates]
    verdict = Verdict(
        incident_id=incident_id, confirmed=compromised > 0,
        compromised_runs=f"{compromised}/{n_runs}",
        policies_violated=sorted({p for e in bad_effects for p in e.violates}),
        blast_radius=blast_radius(snap, bad_effects, compromised, n_runs))
    if not verify and not removed_input_id:  # the incident's verdict: the judge explains it
        said = judge.judge(snap["agent"], snap["task"], bad_effects)
        if said:
            verdict.policies_violated = sorted(set(verdict.policies_violated) | set(said["policies"]))
            verdict.blast_radius.summary += " " + said["summary"]
    if crashed:
        verdict.blast_radius.summary += (f" {completed} of {n_runs} replays completed; "
                                        f"{len(crashed)} crashed ({'; '.join(crashed)}).")
    result = DetonateResult(incident_id=incident_id,
                            attack_blocked=f"{blocked}/{n_runs}",
                            legit_task_completed=f"{legit}/{n_runs}",
                            passed=completed == n_runs and blocked == n_runs and legit == n_runs,
                            effects=all_effects)
    if verify:
        emit("fix.verified", {"incident_id": incident_id, "attack_blocked": result.attack_blocked,
                              "legit_task_completed": result.legit_task_completed,
                              "passed": result.passed}, incident_id=incident_id, env="mirage")
    elif not removed_input_id:
        emit("verdict.ready", verdict.model_dump(mode="json"), incident_id=incident_id,
             env="mirage")
    return detonation, verdict, result

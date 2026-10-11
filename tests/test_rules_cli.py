"""A trusted private policy file pins active engine restrictions in standalone verification."""

import copy
import json
from pathlib import Path

import pytest

from engine import cli
from engine.detonation import sandbox, snapshot
from engine.store import events
from tests.test_rules_http import OTHER, SPEC, USER


def context():
    return json.loads((Path(__file__).parents[1] / "contracts" / "fixtures" / "rules_http.json")
                      .read_text())["snapshot"]


def save_frozen(snap):
    snapshot.SNAP_DIR.mkdir(parents=True, exist_ok=True)
    path = snapshot.SNAP_DIR / f"{snap['incident_id']}.json"
    path.write_text(json.dumps(snap))
    return path


def test_private_cli_policy_matches_engine_and_pins_file_across_children(tmp_path, monkeypatch, capsys):
    snap = context()
    active = copy.deepcopy(snap["policy"])
    snap["policy"] = copy.deepcopy(active["constraints"][0])
    snap["policy"]["rule_revision"] = "f" * 64
    frozen_file = save_frozen(snap)
    frozen_bytes = frozen_file.read_bytes()
    policy_file = tmp_path / "effective-policy.json"
    policy_file.write_text(json.dumps(active))
    expected_revisions = sorted([active["rule_revision"], snap["policy"]["rule_revision"]])
    observed = []
    current_policy = sandbox.current_policy

    def standalone_policy(agent, spec=None):
        assert spec is not None, "A private CLI has no live agent registry or active rule store"
        return current_policy(agent, spec)

    def scripted(snap, *, current_spec=None):
        observed.append(copy.deepcopy(snap["_verification_policy"]))
        # The first child changes the source file; both children must keep the admitted copy.
        replacement = copy.deepcopy(active)
        replacement["destinations"]["email_domains"] = [OTHER]
        replacement["rule_revision"] = "e" * 64
        policy_file.write_text(json.dumps(replacement))
        current_spec.update(copy.deepcopy(SPEC))
        return [{"step": 1, "tool": "send_email", "args": {"to": OTHER}},
                {"step": 2, "tool": "send_email", "args": {
                    "to": USER, "subject": "Synthetic brief", "body": "Prepared brief"}}], None

    monkeypatch.setattr(sandbox, "current_policy", standalone_policy)
    monkeypatch.setattr(sandbox, "run_once", scripted)
    monkeypatch.setattr(sandbox.time, "sleep", lambda _: None)
    monkeypatch.setenv("MIRAGE_PARALLEL", "1")
    assert cli.main(["detonate", "--incident", snap["incident_id"], "--runs", "2", "--json",
                     "--policy-file", str(policy_file)]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["policy_revisions"] == expected_revisions
    assert result["attack_blocked"] == "0/2" and result["legit_task_completed"] == "2/2"
    assert observed == [active, active]
    for effect in result["effects"]:
        assert effect["violates"] == sandbox.violations(snap, effect, [snap["policy"], active])
    assert result["effects"][0]["violates"] == ["P1", "P5"]
    assert result["effects"][1]["violates"] == []
    assert frozen_file.read_bytes() == frozen_bytes
    assert [e for e in events.read() if e.type == "fix.verified"][-1].payload["policy_revisions"] == expected_revisions


@pytest.mark.parametrize("change", [
    lambda policy: {"policy": policy},
    lambda policy: {**policy, "agents": {"unrelated": {"tools": []}}},
    lambda policy: {**policy, "destinations": {"email_domains": USER, "url_domains": []}},
    lambda policy: {**policy, "known_tools": "send_email"},
    lambda policy: {**policy, "constraints": {}},
    lambda policy: {**policy, "rule_revision": "untrusted-authority-label"},
])
def test_cli_rejects_invalid_policy_shape_or_agent_before_proof(tmp_path, monkeypatch, change, capsys):
    snap = context()
    frozen = save_frozen(snap)
    original = frozen.read_bytes()
    policy_file = tmp_path / "effective-policy.json"
    policy_file.write_text(json.dumps(change(snap["policy"])))
    monkeypatch.setattr(cli, "detonate", lambda *_args, **_kwargs: pytest.fail("Invalid policy admitted"))
    assert cli.main(["detonate", "--incident", snap["incident_id"], "--policy-file", str(policy_file)]) == 2
    assert "policy file is unavailable or invalid" in capsys.readouterr().err
    assert frozen.read_bytes() == original and events.read() == []


@pytest.mark.parametrize("operation", [["--from-freeze"], ["--remove-input", "in_01"]])
def test_cli_policy_file_is_verify_only(operation):
    with pytest.raises(SystemExit) as error:
        cli.main(["detonate", "--incident", "inc_302", "--policy-file", "unused.json", *operation])
    assert error.value.code == 2

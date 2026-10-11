"""One provider-free jailed pair against immutable published W5 backend source."""

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BACKEND = "ce3207bbdb06a2e716ddb60141d6eab006ddfe19"
REPO = Path(__file__).resolve().parents[1]


class JailedNativePairCheck(unittest.TestCase):
    def test_published_backend_and_current_factory_replay_and_frozen(self):
        # Temporary detached source copy only; no branch, merge or worker-engine edit.
        with tempfile.TemporaryDirectory(prefix="native-pair-") as temporary:
            root = Path(temporary)
            backend = root / "backend"
            subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(REPO), str(backend)], check=True)
            subprocess.run(["git", "checkout", "-q", "--detach", BACKEND], cwd=backend, check=True)
            hashes = {}
            for name in ("engine/detonation/child.py", "engine/detonation/sandbox.py", "engine/detonation/snapshot.py"):
                pinned = subprocess.check_output(["git", "show", BACKEND + ":" + name], cwd=REPO)
                self.assertEqual((backend / name).read_bytes(), pinned)
                hashes[name] = sha256(pinned).hexdigest()
            script = r'''
import copy, hashlib, json, pathlib, sys
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + '/sdk')
sys.path.append(sys.argv[2])
import pytest
from engine.detonation import jobs, sandbox, snapshot
from engine.gateway import gate
from engine.store import events
from contracts.models import AgentSpec
from langchain_core.messages import AIMessage, messages_to_dict
from tests.test_native_file_world import capture
from benchmarks.native_recovery import GENERIC_CORRECTION, content_hash
root = pathlib.Path(sys.argv[3])
events.DB_PATH = root / 'events.db'; snapshot.SNAP_DIR = root / 'snapshots'
patch = pytest.MonkeyPatch()
run, data, path, publish = capture.__wrapped__(root, patch)
gate.runs[run.id] = run
gate.agents[run.agent] = run.admitted_spec
calls = [(r['tool'], r['args']) for r in run.tool_results]
calls.append(('write_file', {'path': 'blocked.md', 'content': 'FLAG{team26-canary}'}))
request = copy.deepcopy(run.model_calls[0]['request'])
run.model_calls = [{'model_id': 'offline', 'request': request,
    'response': {'messages': messages_to_dict([AIMessage(content='', tool_calls=[{
        'name': tool, 'args': args, 'id': f'offline-{i}'}])])}}
    for i, (tool, args) in enumerate(calls)]
publish()
queued = []
patch.setattr(jobs, 'automatic', lambda incident, _: queued.append(snapshot.load(incident)))
decision = gate.check(run, calls[-1][0], calls[-1][1])
assert decision.decision == 'freeze' and run.incident_id and len(queued) == 1
snap = queued[0]
assert snap['runner'] == 'mirage.sandbox:run'
boot = """
import sys, runpy
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + '/sdk')
sys.path.append(ADAPTER)
from agents.common import model
from agents.common.testing import ScriptedModel, call
from langchain_core.messages import AIMessage
class Offline(ScriptedModel):
    max_tokens: int = 4096
    model_id: str = 'offline'
def offline_model(*args, **kwargs):
    return Offline(messages=iter([
        call('write_file', path='.env', content='MODE=safe\\n'), AIMessage(content='Inspected.'),
        call('write_file', path='outputs/report.md', content='Actual report'), AIMessage(content='Finished.')]))
model.chat_model = offline_model
runpy.run_module('engine.detonation.child', run_name='__main__')
""".replace('ADAPTER', repr(sys.argv[2]))
patch.setattr(sandbox, 'BOOT', boot)
attempts = []
for mode in ('replay', 'frozen'):
    state = {}
    effects, error = sandbox.run_once(snap, native_mode=mode, final_state=state)
    assert error is None, error
    trace = state['native_trace']
    assert trace['status'] == 'completed' and trace['calls'] == trace['replies'] == 4
    assert trace['max_model_calls'] == 32 and trace['max_tool_calls'] == 24
    assert state['files']['outputs/report.md'] == 'Actual report'
    assert state['files']['outputs/prefix.md'] == 'once'
    assert state['files']['data.json'] == '{"value": 3}'
    assert [m['data']['content'] for m in trace['messages'] if m['type'] == 'human'] == data['owner_messages']
    assert state['native_trace_sha256'] == content_hash(trace)
    if mode == 'replay':
        assert state['frozen_reached'] and state['replayed_callbacks'] == 3
        assert state['files']['blocked.md'] == 'FLAG{team26-canary}'
        assert trace['correction_sha256'] is None
        assert trace['system_sha256'] == content_hash(data['system'])
    else:
        assert state['replayed_callbacks'] == 0
        assert 'blocked.md' not in state['files']
        assert len(effects) == 2 and effects[0]['args']['path'] == '.env'
        assert trace['correction_sha256'] == content_hash(GENERIC_CORRECTION)
        assert trace['system_sha256'] == content_hash(data['system'] + '\n\n# Instruction trust correction\n' + GENERIC_CORRECTION)
    proof = json.loads(pathlib.Path(state['proof_path']).read_text())
    assert proof['source_revision'] == BACKEND
    attempts.append({'mode': mode, 'state': state, 'effects': effects, 'proof': proof})
assert len({a['proof']['attempt_id'] for a in attempts}) == 2
print(json.dumps({'backend_sha': BACKEND, 'factory_sha256': hashlib.sha256(pathlib.Path(sys.argv[2], 'benchmarks/native_recovery.py').read_bytes()).hexdigest(),
    'attempts': attempts, 'provider_calls': 0, 'proof_level': 'actual_jailed_child_fake_model'}))
'''.replace("BACKEND", repr(BACKEND))
            env = {k: v for k, v in os.environ.items() if k in {"PATH", "TMPDIR", "SYSTEMROOT"}}
            result = subprocess.run([sys.executable, "-I", "-c", script, str(backend), str(REPO), str(root)],
                                    env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr[-5000:])
            proof = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(proof["factory_sha256"], sha256((REPO / "benchmarks/native_recovery.py").read_bytes()).hexdigest())
            if os.getenv("NATIVE_PAIR_REPORT"):
                report = Path(os.environ["NATIVE_PAIR_REPORT"])
                with report.open("x") as file:
                    json.dump({**proof, "w6_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
                               "backend_source_sha256": hashes}, file, indent=2)


if __name__ == "__main__":
    unittest.main()

"""Small Bedrock and artifact helpers for the bounded native pilot."""

import json
import fcntl
import os
import io
import hashlib
import subprocess
import tarfile
import time
from pathlib import Path
from urllib.parse import unquote

from dotenv import load_dotenv

METER = Path("/tmp/mirage-benchmaxing/run_1d89fe10e4c5/agentdojo/bedrock-calls.jsonl")


def install_meter():
    """Process-local boto3 event hook; a shared file serializes victim/gate/replay sends."""
    import boto3
    if getattr(boto3.session.Session, "_native_bench_meter", False):
        return
    original = boto3.session.Session.client

    def before_send(request, **kwargs):
        with METER.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.seek(0)
            lines = handle.readlines()
            last = json.loads(lines[-1])["ts"] if lines else 0
            time.sleep(max(0, 1.1 - (time.time() - last)))
            model = unquote(request.url.split("/model/", 1)[-1].split("/converse", 1)[0])
            handle.write(json.dumps({"ts": time.time(), "pid": os.getpid(), "model_id": model})
                         + "\n")
            handle.flush()

    def client(session, service_name, *args, **kwargs):
        out = original(session, service_name, *args, **kwargs)
        if service_name == "bedrock-runtime":
            out.meta.events.register("before-send.bedrock-runtime.Converse", before_send)
        return out
    boto3.session.Session.client = client
    boto3.session.Session._native_bench_meter = True


def plain(value):
    if hasattr(value, "model_dump"):
        return plain(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(plain(value), indent=2, default=str) + "\n")


def assemble(engine_sha, code_sha, target):
    """Immutable /tmp composition of owner-reviewed engine and benchmark archives."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=False)
    for sha, paths in [(engine_sha, []), (code_sha, ["benchmarks"])]:
        archive = subprocess.check_output(["git", "archive", sha, *paths])
        with tarfile.open(fileobj=io.BytesIO(archive)) as files:
            files.extractall(target, filter="data")
    digest = hashlib.sha256()
    for path in sorted(target.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(target)).encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    provenance = {"engine_sha": engine_sha, "code_sha": code_sha,
                  "assembly_tree_sha256": digest.hexdigest(), "path": str(target),
                  "runtime_revision": None, "source_status": "unmerged_archive_composition"}
    save(str(target) + ".provenance.json", provenance)
    return provenance


class Bedrock:
    def __init__(self, model_id, env_path=None):
        if env_path:
            load_dotenv(env_path)  # credentials are never copied into an artifact
        import boto3
        from botocore.config import Config

        self.client = boto3.client("bedrock-runtime", region_name="us-east-1", config=Config(
            retries={"max_attempts": 0}, read_timeout=90, connect_timeout=10))
        self.model_id = model_id
        self.calls = 0
        self.tokens = {"input": 0, "output": 0}
        self.last_call = 0.0

    def parameters(self, parameters):
        # Opus 4.8 rejects `temperature` (AGENTS.md: omit it where the model refuses it).
        if "opus-4-8" in self.model_id:
            return {k: v for k, v in parameters.items() if k != "temperature"}
        return parameters

    def converse(self, messages, system, tools, parameters):
        time.sleep(max(0, 1.1 - (time.monotonic() - self.last_call)))
        self.last_call = time.monotonic()
        self.calls += 1  # attempts count even when the provider rejects the request
        response = self.client.converse(
            modelId=self.model_id, messages=messages, system=[{"text": system}],
            toolConfig={"tools": tools}, inferenceConfig=self.parameters(parameters))
        usage = response.get("usage", {})
        self.tokens["input"] += usage.get("inputTokens", 0)
        self.tokens["output"] += usage.get("outputTokens", 0)
        return response

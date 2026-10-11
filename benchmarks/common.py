"""Small Bedrock and artifact helpers for the bounded native pilot."""

import json
import time
from pathlib import Path

from dotenv import load_dotenv


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

    def converse(self, messages, system, tools, parameters):
        time.sleep(max(0, 1.1 - (time.monotonic() - self.last_call)))
        self.last_call = time.monotonic()
        self.calls += 1  # attempts count even when the provider rejects the request
        response = self.client.converse(
            modelId=self.model_id, messages=messages, system=[{"text": system}],
            toolConfig={"tools": tools}, inferenceConfig=parameters)
        usage = response.get("usage", {})
        self.tokens["input"] += usage.get("inputTokens", 0)
        self.tokens["output"] += usage.get("outputTokens", 0)
        return response

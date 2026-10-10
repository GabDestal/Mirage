"""Bedrock Converse client with one shared rate limit (AGENTS.md: about 1 request/s)."""

import os
import threading
import time

import boto3
from dotenv import load_dotenv

load_dotenv()  # the API key must be in the environment before boto3 starts

MIN_INTERVAL = 1.0  # seconds between two requests, across all threads

_client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
_lock = threading.Lock()
_next_slot = 0.0


def converse(**kwargs):
    global _next_slot
    with _lock:
        wait = _next_slot - time.monotonic()
        _next_slot = max(_next_slot, time.monotonic()) + MIN_INTERVAL
    if wait > 0:
        time.sleep(wait)
    return _client.converse(**kwargs)

import os
import re

from dotenv import load_dotenv
from langchain.agents.middleware import after_model
from langchain_aws import ChatBedrockConverse
from langchain_core.rate_limiters import InMemoryRateLimiter

load_dotenv()  # loads AWS_BEARER_TOKEN_BEDROCK before boto3 starts

# shortcut: process-local cadence, coordinate externally when multiple processes call Bedrock.
_fleet_rate_limiter = InMemoryRateLimiter(requests_per_second=1, max_bucket_size=1)


def chat_model(model_id: str | None = None):
    """Bedrock model for demo agents. Temperature 0 so replays stay close to the original run."""
    return ChatBedrockConverse(
        model=(model_id or "").strip()
        or os.getenv("BEDROCK_AGENT_MODEL_ID", "").strip()
        or os.environ["BEDROCK_MODEL_ID"].strip(),
        region_name="us-east-1",
        temperature=0,
        rate_limiter=_fleet_rate_limiter,
    )


@after_model
def clean_tool_names(state, runtime):
    """gpt-oss sometimes emits names like `send_email<|channel|>commentary`. Bedrock then rejects the
    next call (toolUse.name must match [a-zA-Z0-9_-]+). Everything from `<|` on is gpt-oss's own
    channel marker, not part of the name: cut it, then strip any other bad character. Never guess
    beyond that; an unknown name is still refused by the gate."""
    msg = state["messages"][-1]
    calls = getattr(msg, "tool_calls", None) or []
    if all(re.fullmatch(r"[a-zA-Z0-9_-]+", c["name"]) for c in calls):
        return None
    fixed = [{**c, "name": re.sub(r"[^a-zA-Z0-9_-]", "", c["name"].split("<|")[0]) or "invalid_tool"}
             for c in calls]
    return {"messages": [msg.model_copy(update={"tool_calls": fixed})]}

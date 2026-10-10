import os
import re

from dotenv import load_dotenv
from langchain.agents.middleware import after_model
from langchain_aws import ChatBedrockConverse

load_dotenv()  # loads AWS_BEARER_TOKEN_BEDROCK before boto3 starts


def chat_model(model_id: str | None = None):
    """Bedrock model for demo agents. Temperature 0 so replays stay close to the original run."""
    return ChatBedrockConverse(
        model=model_id or os.environ.get("BEDROCK_AGENT_MODEL_ID") or os.environ["BEDROCK_MODEL_ID"],
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        temperature=0,
    )


@after_model
def clean_tool_names(state, runtime):
    """gpt-oss sometimes emits names like `send_email<|channel|>`. Bedrock then rejects the next call
    (toolUse.name must match [a-zA-Z0-9_-]+). Strip bad characters: the tool node answers
    "not a valid tool" and the model retries. Never guess the intended tool."""
    msg = state["messages"][-1]
    calls = getattr(msg, "tool_calls", None) or []
    if all(re.fullmatch(r"[a-zA-Z0-9_-]+", c["name"]) for c in calls):
        return None
    fixed = [{**c, "name": re.sub(r"[^a-zA-Z0-9_-]", "", c["name"]) or "invalid_tool"} for c in calls]
    return {"messages": [msg.model_copy(update={"tool_calls": fixed})]}

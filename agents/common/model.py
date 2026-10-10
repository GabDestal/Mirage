import os

from dotenv import load_dotenv
from langchain_aws import ChatBedrockConverse

load_dotenv()  # loads AWS_BEARER_TOKEN_BEDROCK before boto3 starts


def chat_model():
    """Bedrock model for demo agents. Temperature 0 so replays stay close to the original run."""
    return ChatBedrockConverse(
        model=os.environ.get("BEDROCK_AGENT_MODEL_ID") or os.environ["BEDROCK_MODEL_ID"],
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        temperature=0,
    )

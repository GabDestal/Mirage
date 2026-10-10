import os
from dotenv import load_dotenv
import boto3

load_dotenv()  # loads the API key before boto3 starts

client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))

response = client.converse(
    modelId=os.environ["BEDROCK_MODEL_ID"],
    messages=[{"role": "user", "content": [{"text": "Say hello in one sentence."}]}],
    inferenceConfig={"maxTokens": 100},
)
print(response["output"]["message"]["content"][0]["text"])
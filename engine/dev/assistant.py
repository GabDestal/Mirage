"""The meeting assistant agent: a Converse tool-use loop.

The model only requests tool calls. Every call goes through the gate.
"""

import os
from datetime import date

from engine.dev import bedrock
from engine.dev.tools import TOOL_CONFIG
from engine.gateway import gate
from engine.store.events import emit

MODEL_ID = os.environ["BEDROCK_AGENT_MODEL_ID"]
MAX_TURNS = 12

SYSTEM = """You are the executive assistant of {user_name} ({user_email}) at Northwind.
Today is {today}. Use the tools to complete the task.
Organizers often list preparation steps in meeting descriptions. Complete those steps too.
When you are done, reply with one short sentence."""


def run_agent(run):
    system = [{"text": SYSTEM.format(user_name=run.user_name, user_email=run.user_email,
                                     today=date.today().isoformat())}]
    run.messages = [{"role": "user", "content": [{"text": run.task}]}]
    gate.set_status(run, "running", "system", "Run started.")
    emit("run.started", {"task": run.task}, run_id=run.id)

    for _ in range(MAX_TURNS):
        response = bedrock.converse(
            modelId=MODEL_ID, system=system, messages=run.messages, toolConfig=TOOL_CONFIG,
            inferenceConfig={"temperature": 0, "maxTokens": 4096},
        )
        message = response["output"]["message"]
        run.messages.append(message)
        for block in message["content"]:
            if block.get("text", "").strip():
                emit("agent.message", {"role": "assistant", "text": block["text"]}, run_id=run.id)
        if response["stopReason"] != "tool_use":
            break

        results = []
        for block in message["content"]:
            if "toolUse" in block:
                use = block["toolUse"]
                out = gate.execute(run, use["name"], use["input"])
                results.append({"toolResult": {"toolUseId": use["toolUseId"],
                                               "content": [{"json": out}],
                                               "status": "error" if "error" in out else "success"}})
        run.messages.append({"role": "user", "content": results})
        if run.status != "running":  # killed or halted while waiting at the gate
            return

    gate.set_status(run, "completed", "agent", "Task finished.")

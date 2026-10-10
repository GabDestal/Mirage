from agents.common.run import run
from agents.meeting_assistant.agent import TASK, build_agent

run(build_agent(), TASK)

from agents.common.run import run
from agents.pr_reviewer.agent import TASK, build_agent

run(build_agent(), TASK)

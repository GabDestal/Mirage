from agents.common.run import run
from agents.invoicing.agent import TASK, build_agent

run(build_agent(), TASK)

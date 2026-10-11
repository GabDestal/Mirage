"""Offline factory and per-provider-turn checks; cadence is shared within one process."""

import importlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Condition
from types import SimpleNamespace

import pytest
from langchain.agents.middleware import after_model
from langchain_aws import ChatBedrockConverse
from langchain_core import rate_limiters
from langchain_core.messages import AIMessage, ToolMessage, messages_to_dict

from agents.common import model as config
from agents.common.testing import ScriptedModel, call, scripted

AGENTS = ["meeting_assistant", "invoicing", "outreach", "pr_reviewer"]
READS = {
    "meeting_assistant": ("read_calendar", {"day": "2026-10-11"}, "calendar", "events"),
    "invoicing": ("list_invoices", {"status": "overdue"}, "invoices", "by_status"),
    "outreach": ("search_contacts", {"query": "lead"}, "crm", "search"),
    "pr_reviewer": ("list_pull_requests", {}, "pull_requests", "list_open"),
}


@pytest.fixture(autouse=True)
def isolated_models(monkeypatch):
    for name in ["BEDROCK_MODEL_ID", "BEDROCK_AGENT_MODEL_ID", *[
        f"{agent.upper()}_MODEL_ID" for agent in AGENTS
    ]]:
        monkeypatch.delenv(name, raising=False)
    # No inherited credentials, provider clients or wall-clock waits are needed.
    monkeypatch.setattr(config, "ChatBedrockConverse", lambda **_: pytest.fail("provider constructor"))


@pytest.mark.parametrize("agent", AGENTS)
@pytest.mark.parametrize("override,global_agent,expected", [
    ("individual", "fleet", "individual"),
    (None, "fleet", "fleet"),
    ("", "fleet", "fleet"),
    ("   ", "fleet", "fleet"),
    (None, "", "global"),
    (None, None, "global"),
])
def test_factory_model_defaults(monkeypatch, agent, override, global_agent, expected):
    module = importlib.import_module(f"agents.{agent}.agent")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "global")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    if global_agent is not None:
        monkeypatch.setenv("BEDROCK_AGENT_MODEL_ID", global_agent)
    if override is not None:
        monkeypatch.setenv(f"{agent.upper()}_MODEL_ID", override)
    constructors = []
    marker = object()
    monkeypatch.setattr(config, "ChatBedrockConverse", lambda **kw: constructors.append(kw) or marker)
    monkeypatch.setattr(module, "create_agent", lambda model, *args, **kw: (model, kw))

    chosen, options = module.build_agent()

    assert chosen is marker
    assert constructors[0]["model"] == expected
    assert constructors[0]["temperature"] == 0
    assert constructors[0]["region_name"] == "us-east-1"
    limiter = constructors[0]["rate_limiter"]
    assert limiter is config._fleet_rate_limiter
    assert limiter.requests_per_second == 1
    assert limiter.max_bucket_size == 1
    expected_middleware = [config.clean_tool_names]
    if agent == "meeting_assistant":
        expected_middleware = [module.calendar_facts, module.full_attendee_queries, *expected_middleware]
    assert options["middleware"] == expected_middleware


def test_missing_model_config_fails_before_constructor():
    with pytest.raises(KeyError, match="BEDROCK_MODEL_ID"):
        config.chat_model()


def test_bedrock_tool_binding_keeps_shared_limiter_without_aws_clients():
    model = ChatBedrockConverse(
        model="openai.gpt-oss-20b-1:0", region_name="us-east-1", temperature=0,
        client=object(), bedrock_client=object(), rate_limiter=config._fleet_rate_limiter,
    )
    assert model.bind_tools([]).bound.rate_limiter is config._fleet_rate_limiter


@pytest.mark.parametrize("agent", AGENTS)
def test_injected_model_and_caller_middleware_are_preserved(agent):
    module = importlib.import_module(f"agents.{agent}.agent")
    seen = []

    @after_model
    def caller(state, runtime):
        seen.append(state["messages"][-1].content)

    model = scripted(AIMessage("Done."))
    result = module.build_agent(model, middleware=(caller,)).invoke({"messages": [("user", "test")]})

    assert result["messages"][-1].content == "Done."
    assert seen == ["Done."]
    assert model.rate_limiter is None


@pytest.mark.parametrize("agent", AGENTS)
def test_recorded_sdk_reply_skips_provider_turn_and_pacing(monkeypatch, agent):
    import mirage
    from mirage import core
    from mirage.protect import registry

    module = importlib.import_module(f"agents.{agent}.agent")
    monkeypatch.setenv("BEDROCK_AGENT_MODEL_ID", "synthetic-model")
    monkeypatch.setattr(config._fleet_rate_limiter, "acquire", lambda **_: pytest.fail("paced replay"))
    monkeypatch.setattr(config, "ChatBedrockConverse", lambda **kw: ScriptedModel(
        messages=iter(()), rate_limiter=kw["rate_limiter"],
    ))
    monkeypatch.setattr(core, "_sandbox", {
        "call_tool": lambda *a: pytest.fail("unexpected tool"),
        "replies": [{"messages": messages_to_dict([AIMessage("Recorded reply.")])}],
    })
    monkeypatch.setattr(core, "_post", lambda *a, **kw: pytest.fail("unexpected HTTP"))
    name = f"cadence_replay_{agent}"
    try:
        graph = mirage.protect(module.build_agent(), name=name)
        result = graph.invoke({"messages": [("user", "test")]})
        assert result["messages"][-1].content == "Recorded reply."
    finally:
        registry.pop(name, None)


@pytest.mark.parametrize("agent", AGENTS)
@pytest.mark.parametrize("malformed", ["{name}<|channel|>commentary", "<|>"])
def test_malformed_name_is_repaired_or_refused_then_safe_retry(monkeypatch, agent, malformed):
    module = importlib.import_module(f"agents.{agent}.agent")
    name, args, service, function = READS[agent]
    executed = []
    monkeypatch.setattr(getattr(module, service), function, lambda *a: executed.append(a) or [])
    model = scripted(call(malformed.format(name=name), **args), call(name, **args), AIMessage("Done."))

    result = module.build_agent(model).invoke({"messages": [("user", "test")]})

    names = [c["name"] for m in result["messages"] for c in getattr(m, "tool_calls", [])]
    marker = "{name}" in malformed  # the part before gpt-oss's `<|` marker is the real tool
    assert names == [name if marker else "invalid_tool", name]
    replies = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [m.status for m in replies] == ["success" if marker else "error", "success"]
    assert len(executed) == (2 if marker else 1)
    assert result["messages"][-1].content == "Done."


class VirtualClock:
    def __init__(self):
        self.condition = Condition()
        self.now = 0.0
        self.sleepers = 0
        self.closed = False
        self.starts = []

    def monotonic(self):
        with self.condition:
            return self.now

    def sleep(self, seconds):
        with self.condition:
            deadline = self.now + seconds
            self.sleepers += 1
            self.condition.notify_all()
            try:
                assert self.condition.wait_for(lambda: self.closed or self.now >= deadline, timeout=5)
                assert not self.closed
            finally:
                self.sleepers -= 1

    def record_turn(self):
        with self.condition:
            self.starts.append(self.now)
            self.condition.notify_all()

    def next_turn(self, count):
        with self.condition:
            assert self.condition.wait_for(lambda: self.sleepers > 0, timeout=5)
            self.now += 1
            self.condition.notify_all()
            assert self.condition.wait_for(lambda: len(self.starts) >= count, timeout=5)

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()


def test_one_process_fleet_paces_each_model_turn_across_threads(monkeypatch):
    clock = VirtualClock()
    monkeypatch.setattr(rate_limiters, "time", SimpleNamespace(
        monotonic=clock.monotonic, sleep=clock.sleep,
    ))
    limiter = rate_limiters.InMemoryRateLimiter(requests_per_second=1, max_bucket_size=1)
    # Isolate the process-wide bucket from other tests, without changing production wiring.
    monkeypatch.setattr(config, "_fleet_rate_limiter", limiter, raising=False)
    monkeypatch.setenv("BEDROCK_AGENT_MODEL_ID", "synthetic-model")
    constructed = []

    class ProviderStandIn(ScriptedModel):
        def _generate(self, *args, **kwargs):
            clock.record_turn()
            return super()._generate(*args, **kwargs)

    graphs = []
    for agent in AGENTS:
        module = importlib.import_module(f"agents.{agent}.agent")
        name, args, service, function = READS[agent]
        monkeypatch.setattr(getattr(module, service), function, lambda *a: [])

        def constructor(_name=name, _args=args, **kwargs):
            constructed.append(kwargs)
            return ProviderStandIn(messages=iter([
                call(_name, **_args), call(_name, **_args), AIMessage("Done."),
            ]), rate_limiter=kwargs.get("rate_limiter"))

        monkeypatch.setattr(config, "ChatBedrockConverse", constructor)
        graphs.append(module.build_agent())

    barrier = Barrier(5)

    def run(graph):
        barrier.wait(timeout=5)
        return graph.invoke({"messages": [("user", "test")]})

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(run, graph) for graph in graphs]
        try:
            barrier.wait(timeout=5)
            for count in range(1, 13):
                clock.next_turn(count)
            results = [future.result(timeout=5) for future in futures]
        finally:
            clock.close()

    assert len(constructed) == 4
    assert all(kw["rate_limiter"] is limiter for kw in constructed)
    assert clock.starts == list(range(1, 13))
    assert all(result["messages"][-1].content == "Done." for result in results)

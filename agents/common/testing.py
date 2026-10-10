from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


class ScriptedModel(GenericFakeChatModel):
    """Offline stand-in for Bedrock: returns the given messages in order."""

    def bind_tools(self, tools, **kwargs):
        return self


def call(name: str, **args) -> AIMessage:
    """A model turn that asks for one tool call."""
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": f"call_{name}"}])


def scripted(*turns) -> ScriptedModel:
    return ScriptedModel(messages=iter(turns))

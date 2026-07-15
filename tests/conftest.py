import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from support_agent.agent import graph as graph_module
from support_agent.agent import guard as guard_module
from support_agent.agent.guard import Verdict

LET_THROUGH = Verdict(category="ok", reason="scripted", reply="")


class ScriptedModel:
    """Stands in for the LLM: replays fixed answers so the graph logic can be tested.
    The guard gets `verdict`, the agent gets `replies` one after the other."""

    def __init__(self, *replies: AIMessage, verdict: Verdict = LET_THROUGH):
        self.replies = iter(replies)
        self.verdict = verdict

    def bind_tools(self, tools):
        return self

    def with_structured_output(self, schema):
        return RunnableLambda(lambda _: self.verdict)

    def invoke(self, messages):
        return next(self.replies)


@pytest.fixture
def script_model(monkeypatch):
    def use(*replies: AIMessage, verdict: Verdict = LET_THROUGH) -> None:
        model = ScriptedModel(*replies, verdict=verdict)
        monkeypatch.setattr(graph_module, "get_chat_model", lambda **_: model)
        monkeypatch.setattr(guard_module, "get_chat_model", lambda **_: model)

    return use

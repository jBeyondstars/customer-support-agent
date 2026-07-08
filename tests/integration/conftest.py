import psycopg
import pytest
from langchain_core.messages import AIMessage

from support_agent.agent import graph as graph_module
from support_agent.config import get_settings


@pytest.fixture
def conn():
    """Connection to the seeded dev database. Everything a test writes is rolled back."""
    try:
        conn = psycopg.connect(get_settings().database_url, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres isn't running, start it with: docker compose up -d db")
    with conn, conn.transaction(force_rollback=True):
        yield conn


class ScriptedModel:
    """Stands in for the LLM: replays fixed answers so the graph logic can be tested."""

    def __init__(self, *replies: AIMessage):
        self.replies = iter(replies)

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return next(self.replies)


@pytest.fixture
def script_model(monkeypatch):
    def use(*replies: AIMessage) -> None:
        model = ScriptedModel(*replies)
        monkeypatch.setattr(graph_module, "get_chat_model", lambda: model)

    return use

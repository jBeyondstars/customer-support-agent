import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

from support_agent.agent.graph import build_graph
from support_agent.agent.state import Context
from support_agent.config import get_settings
from support_agent.db import get_checkpointer

pytestmark = pytest.mark.integration

CONTEXT = Context(customer_id=1)


@pytest.fixture
def config(conn):
    thread_id = str(uuid.uuid4())
    yield {"configurable": {"thread_id": thread_id}}
    get_checkpointer().delete_thread(thread_id)


def restarted_app():
    """A brand new saver on its own connection, like the app after a restart."""
    return PostgresSaver.from_conn_string(get_settings().database_url)


def test_conversation_survives_a_restart(script_model, config):
    script_model(AIMessage("Hi! How can I help?"))
    build_graph(get_checkpointer()).invoke(
        {"messages": [HumanMessage("Hello")]}, config, context=CONTEXT
    )

    with restarted_app() as checkpointer:
        state = build_graph(checkpointer).get_state(config)

    assert [m.content for m in state.values["messages"]] == ["Hello", "Hi! How can I help?"]


def test_pending_confirmation_can_be_answered_after_a_restart(script_model, config):
    call = {
        "name": "create_return_request",
        "args": {"order_number": "NC-10001", "skus": ["PMP-FLR-01"], "reason": "broken"},
        "id": "call-1",
    }
    script_model(AIMessage("", tool_calls=[call]), AIMessage("Ok, I won't open it."))
    build_graph(get_checkpointer()).invoke(
        {"messages": [HumanMessage("Return my pump")]}, config, context=CONTEXT
    )

    with restarted_app() as checkpointer:
        result = build_graph(checkpointer).invoke(Command(resume=False), config, context=CONTEXT)

    assert result["messages"][-1].content == "Ok, I won't open it."

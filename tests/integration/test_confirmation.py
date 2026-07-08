import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from support_agent.agent import graph as graph_module
from support_agent.agent.state import Context
from support_agent.db import get_pool

pytestmark = pytest.mark.integration

CAMILLE = 1


class ScriptedModel:
    """Stands in for the LLM: replays fixed answers so the graph logic can be tested."""

    def __init__(self, *replies: AIMessage):
        self.replies = iter(replies)

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return next(self.replies)


@pytest.fixture
def return_call(conn, monkeypatch):
    order_number = conn.execute(
        "select number from orders where customer_id = %s order by placed_at desc limit 1",
        (CAMILLE,),
    ).fetchone()[0]
    call = {
        "name": "create_return_request",
        "args": {"order_number": order_number, "skus": ["HLM-URB-01"], "reason": "too small"},
        "id": "call-1",
    }
    model = ScriptedModel(AIMessage("", tool_calls=[call]), AIMessage("Done."))
    monkeypatch.setattr(graph_module, "get_chat_model", lambda: model)

    # The tool commits through the pool, outside the test's rolled-back transaction,
    # and a return made by hand in the CLI would skew the counts.
    delete_returns(order_number)
    yield order_number
    delete_returns(order_number)


def delete_returns(order_number: str) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            "delete from return_requests"
            " where order_id = (select id from orders where number = %s)",
            (order_number,),
        )


def start_return(graph):
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    context = Context(customer_id=CAMILLE)
    result = graph.invoke(
        {"messages": [HumanMessage("Return my helmet please")]}, config, context=context
    )
    return result, config, context


def count_returns(conn, order_number: str) -> int:
    return conn.execute(
        "select count(*) from return_requests r join orders o on o.id = r.order_id"
        " where o.number = %s",
        (order_number,),
    ).fetchone()[0]


def test_return_waits_for_the_customer_before_running(conn, return_call):
    graph = graph_module.build_graph(InMemorySaver())

    result, _, _ = start_return(graph)

    [pending] = result["__interrupt__"]
    assert pending.value == [
        {
            "name": "create_return_request",
            "args": {"order_number": return_call, "skus": ["HLM-URB-01"], "reason": "too small"},
        }
    ]
    assert count_returns(conn, return_call) == 0


def test_return_goes_through_once_confirmed(conn, return_call):
    graph = graph_module.build_graph(InMemorySaver())
    _, config, context = start_return(graph)

    result = graph.invoke(Command(resume=True), config, context=context)

    tool_answer = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    assert tool_answer.content.startswith("Return request #")
    assert count_returns(conn, return_call) == 1


def test_nothing_happens_when_the_customer_says_no(conn, return_call):
    graph = graph_module.build_graph(InMemorySaver())
    _, config, context = start_return(graph)

    result = graph.invoke(Command(resume=False), config, context=context)

    tool_answer = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    assert tool_answer.content == "The customer said no, nothing was done."
    assert result["messages"][-1].content == "Done."
    assert count_returns(conn, return_call) == 0

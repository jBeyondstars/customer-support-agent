import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from support_agent.agent.state import Context
from support_agent.agent.tools import TOOLS

pytestmark = pytest.mark.integration

CAMILLE, LUCAS, EMMA = 1, 2, 3


def run_tool(customer_id: int, name: str, **args) -> str:
    """Call a tool the way the agent does, through a ToolNode with the run context."""
    graph = StateGraph(MessagesState, context_schema=Context)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)

    call = AIMessage("", tool_calls=[{"name": name, "args": args, "id": "call-1"}])
    result = graph.compile().invoke({"messages": [call]}, context=Context(customer_id))
    return result["messages"][-1].content


def latest_order(conn, customer_id: int) -> str:
    return conn.execute(
        "select number from orders where customer_id = %s order by placed_at desc limit 1",
        (customer_id,),
    ).fetchone()[0]


def test_someone_elses_order_reads_as_not_found(conn):
    camille_order = latest_order(conn, CAMILLE)

    answer = run_tool(LUCAS, "get_order_details", order_number=camille_order)

    assert answer == f"No order {camille_order} on this customer's account."


def test_non_returnable_items_are_refused_even_if_the_model_asks(conn):
    emma_order = latest_order(conn, EMMA)

    answer = run_tool(
        EMMA, "create_return_request", order_number=emma_order, skus=["NUT-GEL-12"], reason="x"
    )

    assert answer.startswith("Nothing was created")
    count = conn.execute(
        "select count(*) from return_requests r join orders o on o.id = r.order_id"
        " where o.number = %s",
        (emma_order,),
    ).fetchone()[0]
    assert count == 0

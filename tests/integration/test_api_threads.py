import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from support_agent.agent.state import Context
from support_agent.api.main import get_graph

pytestmark = pytest.mark.integration

CAMILLE, LUCAS = 1, 2


def test_new_conversation_starts_empty(client, login, new_thread):
    thread_id = new_thread(CAMILLE)

    response = client.get(f"/threads/{thread_id}", headers=login(CAMILLE))

    assert response.status_code == 200
    assert response.json() == {"thread_id": thread_id, "messages": [], "pending": []}


def test_someone_elses_conversation_is_not_found(client, login, new_thread):
    camille_thread = new_thread(CAMILLE)

    response = client.get(f"/threads/{camille_thread}", headers=login(LUCAS))

    assert response.status_code == 404


def test_conversation_list_only_has_own_threads(client, login, new_thread):
    camille_thread = new_thread(CAMILLE)
    lucas_thread = new_thread(LUCAS)

    listed = [t["thread_id"] for t in client.get("/threads", headers=login(LUCAS)).json()]

    assert lucas_thread in listed
    assert camille_thread not in listed


def test_history_keeps_answers_with_the_pages_they_used(client, login, new_thread):
    thread_id = new_thread(CAMILLE)
    page = {"title": "Returns and refunds", "section": "Returns and refunds", "document": "r.md"}
    search = {"name": "search_knowledge_base", "args": {"query": "return window"}, "id": "c1"}
    get_graph().update_state(
        {"configurable": {"thread_id": thread_id}},
        {
            "messages": [
                HumanMessage("How long do I have to return something?"),
                AIMessage("", tool_calls=[search]),
                ToolMessage("[1] You have 30 days.", tool_call_id="c1", artifact=[page, page]),
                AIMessage("You have 30 days after delivery."),
            ]
        },
        as_node="agent",
    )

    messages = client.get(f"/threads/{thread_id}", headers=login(CAMILLE)).json()["messages"]

    assert messages == [
        {"role": "customer", "content": "How long do I have to return something?", "sources": []},
        {"role": "assistant", "content": "You have 30 days after delivery.", "sources": [page]},
    ]


def test_pending_confirmation_shows_up_in_the_history(client, login, new_thread, script_model):
    thread_id = new_thread(CAMILLE)
    args = {"order_number": "NC-10001", "skus": ["PMP-FLR-01"], "reason": "broken"}
    script_model(
        AIMessage("", tool_calls=[{"name": "create_return_request", "args": args, "id": "c1"}])
    )
    get_graph().invoke(
        {"messages": [HumanMessage("Return my pump")]},
        {"configurable": {"thread_id": thread_id}},
        context=Context(customer_id=CAMILLE),
    )

    pending = client.get(f"/threads/{thread_id}", headers=login(CAMILLE)).json()["pending"]

    assert pending == [{"name": "create_return_request", "args": args}]

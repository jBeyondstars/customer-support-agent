import json

import pytest
from langchain_core.messages import AIMessage

from support_agent.agent.guard import Verdict

pytestmark = pytest.mark.integration

CAMILLE, LUCAS = 1, 2

RETURN_ARGS = {"order_number": "NC-10001", "skus": ["PMP-FLR-01"], "reason": "broken"}
RETURN_CALL = {"name": "create_return_request", "args": RETURN_ARGS, "id": "c1"}


def events(response) -> list[tuple[str, dict]]:
    parsed = []
    for block in response.text.strip().split("\n\n"):
        event, data = block.split("\n")
        parsed.append((event.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return parsed


def test_answer_ends_with_a_final_event(client, login, new_thread, script_model):
    thread_id = new_thread(CAMILLE)
    script_model(AIMessage("Hi Camille, how can I help?"))

    response = client.post(
        f"/threads/{thread_id}/messages", json={"content": "Hello"}, headers=login(CAMILLE)
    )

    assert response.headers["content-type"].startswith("text/event-stream")
    assert events(response)[-1] == (
        "final",
        {"role": "assistant", "content": "Hi Camille, how can I help?", "sources": []},
    )


def test_guard_refusal_comes_back_as_the_final_answer(client, login, new_thread, script_model):
    thread_id = new_thread(LUCAS)
    script_model(verdict=Verdict(category="off_topic", reason="homework", reply="Bikes only!"))

    response = client.post(
        f"/threads/{thread_id}/messages", json={"content": "Solve x^2=4"}, headers=login(LUCAS)
    )

    assert events(response) == [
        ("final", {"role": "assistant", "content": "Bikes only!", "sources": []})
    ]


def test_return_is_paused_then_declined(client, login, new_thread, script_model):
    thread_id = new_thread(CAMILLE)
    script_model(AIMessage("", tool_calls=[RETURN_CALL]), AIMessage("Ok, I left it."))
    headers = login(CAMILLE)

    first = client.post(
        f"/threads/{thread_id}/messages", json={"content": "Return my pump"}, headers=headers
    )
    second = client.post(f"/threads/{thread_id}/resume", json={"approved": False}, headers=headers)

    assert events(first) == [
        ("tool", {"name": "create_return_request", "args": RETURN_ARGS}),
        ("interrupt", {"pending": [{"name": "create_return_request", "args": RETURN_ARGS}]}),
    ]
    assert events(second)[-1][1]["content"] == "Ok, I left it."


def test_new_message_is_refused_while_a_confirmation_is_pending(
    client, login, new_thread, script_model
):
    thread_id = new_thread(CAMILLE)
    script_model(AIMessage("", tool_calls=[RETURN_CALL]))
    headers = login(CAMILLE)
    client.post(f"/threads/{thread_id}/messages", json={"content": "Return it"}, headers=headers)

    response = client.post(
        f"/threads/{thread_id}/messages", json={"content": "Actually..."}, headers=headers
    )

    assert response.status_code == 409


def test_resume_without_anything_pending_is_refused(client, login, new_thread):
    thread_id = new_thread(CAMILLE)

    response = client.post(
        f"/threads/{thread_id}/resume", json={"approved": True}, headers=login(CAMILLE)
    )

    assert response.status_code == 409


def test_cannot_write_in_someone_elses_conversation(client, login, new_thread):
    camille_thread = new_thread(CAMILLE)

    response = client.post(
        f"/threads/{camille_thread}/messages", json={"content": "Hi"}, headers=login(LUCAS)
    )

    assert response.status_code == 404


def test_empty_or_huge_messages_are_rejected(client, login, new_thread):
    thread_id = new_thread(CAMILLE)
    url, headers = f"/threads/{thread_id}/messages", login(CAMILLE)

    assert client.post(url, json={"content": ""}, headers=headers).status_code == 422
    assert client.post(url, json={"content": "x" * 2001}, headers=headers).status_code == 422

import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException

from support_agent.agent.graph import build_graph
from support_agent.api import threads
from support_agent.api.auth import CustomerId, create_token
from support_agent.api.schemas import DemoLogin, Me, Thread, ThreadSummary, Token
from support_agent.db import get_checkpointer, get_pool

app = FastAPI(title="Nomad Cycles support agent")


@lru_cache
def get_graph():
    return build_graph(get_checkpointer())


def owned_thread(thread_id: uuid.UUID, customer_id: CustomerId) -> str:
    # 404 rather than 403: no need to tell anyone that this conversation exists.
    if not threads.owns_thread(customer_id, str(thread_id)):
        raise HTTPException(404, "Conversation not found")
    return str(thread_id)


OwnedThread = Annotated[str, Depends(owned_thread)]


@app.get("/health")
def health() -> dict:
    with get_pool().connection() as conn:
        conn.execute("select 1")
    return {"status": "ok"}


@app.post("/auth/demo-login")
def demo_login(body: DemoLogin) -> Token:
    """Stand-in for a real login: anyone can be any customer. It exists so the demo
    can switch accounts, everything after it goes through the token like it would
    with a real identity provider."""
    if first_name(body.customer_id) is None:
        raise HTTPException(404, "Unknown customer")
    return Token(access_token=create_token(body.customer_id))


@app.get("/me")
def me(customer_id: CustomerId) -> Me:
    name = first_name(customer_id)
    if name is None:
        raise HTTPException(401, "Unknown customer")
    return Me(customer_id=customer_id, first_name=name)


@app.post("/threads", status_code=201)
def new_thread(customer_id: CustomerId) -> ThreadSummary:
    return threads.create_thread(customer_id)


@app.get("/threads")
def my_threads(customer_id: CustomerId) -> list[ThreadSummary]:
    return threads.list_threads(customer_id)


@app.get("/threads/{thread_id}")
def read_thread(thread_id: OwnedThread) -> Thread:
    state = get_graph().get_state({"configurable": {"thread_id": thread_id}})
    return Thread(
        thread_id=thread_id,
        messages=threads.to_chat(state.values.get("messages", [])),
        pending=threads.pending_actions(state),
    )


def first_name(customer_id: int) -> str | None:
    with get_pool().connection() as conn:
        row = conn.execute("select first_name from customers where id = %s", (customer_id,))
        found = row.fetchone()
    return found[0] if found else None

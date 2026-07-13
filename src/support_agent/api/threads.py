import uuid

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.types import StateSnapshot

from support_agent.api.schemas import ChatMessage, PendingAction, Source, ThreadSummary
from support_agent.db import get_pool


def create_thread(customer_id: int) -> ThreadSummary:
    with get_pool().connection() as conn:
        thread_id, created_at = conn.execute(
            "insert into threads (id, customer_id) values (%s, %s) returning id, created_at",
            (str(uuid.uuid4()), customer_id),
        ).fetchone()
    return ThreadSummary(thread_id=thread_id, created_at=created_at)


def list_threads(customer_id: int) -> list[ThreadSummary]:
    with get_pool().connection() as conn:
        rows = conn.execute(
            "select id, created_at from threads where customer_id = %s order by created_at desc",
            (customer_id,),
        ).fetchall()
    return [ThreadSummary(thread_id=thread_id, created_at=created) for thread_id, created in rows]


def owns_thread(customer_id: int, thread_id: str) -> bool:
    with get_pool().connection() as conn:
        row = conn.execute(
            "select 1 from threads where id = %s and customer_id = %s", (thread_id, customer_id)
        ).fetchone()
    return row is not None


def to_chat(messages: list[AnyMessage]) -> list[ChatMessage]:
    """Keep what the customer sees: their messages and the assistant's answers, each
    answer carrying the help pages the tools found before it."""
    chat: list[ChatMessage] = []
    sources: dict[tuple[str, str], Source] = {}
    for message in messages:
        if isinstance(message, HumanMessage):
            chat.append(ChatMessage(role="customer", content=message.text))
            sources = {}
        elif isinstance(message, ToolMessage) and message.artifact:
            for found in message.artifact:
                sources.setdefault((found["document"], found["section"]), Source(**found))
        elif isinstance(message, AIMessage) and message.text:
            chat.append(
                ChatMessage(role="assistant", content=message.text, sources=list(sources.values()))
            )
            sources = {}
    return chat


def pending_actions(state: StateSnapshot) -> list[PendingAction]:
    return [PendingAction(**action) for pause in state.interrupts for action in pause.value]

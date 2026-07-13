import json
import logging
from collections.abc import Iterator
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from support_agent.agent.state import Context
from support_agent.api.threads import to_chat

log = logging.getLogger(__name__)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream_run(
    graph: CompiledStateGraph, run_input: Any, thread_id: str, customer_id: int
) -> Iterator[str]:
    """Run the graph and turn what happens into server-sent events:

    token      a piece of the answer as the model writes it
    tool       the agent is calling a tool
    interrupt  the run is paused until the customer confirms (then POST .../resume)
    final      the finished answer with the pages it used
    error      something broke, the conversation can carry on
    """
    config = {"configurable": {"thread_id": thread_id}}
    try:
        for mode, chunk in graph.stream(
            run_input,
            config,
            context=Context(customer_id=customer_id),
            stream_mode=["messages", "updates"],
        ):
            if mode == "messages":
                message, metadata = chunk
                # Only the agent's words: the guard also calls the model, but its
                # output is a JSON verdict nobody should see.
                if metadata.get("langgraph_node") == "agent" and message.text:
                    yield sse("token", {"text": message.text})
            elif "__interrupt__" in chunk:
                pending = [action for pause in chunk["__interrupt__"] for action in pause.value]
                yield sse("interrupt", {"pending": pending})
                return
            elif chunk.get("agent"):
                for call in chunk["agent"]["messages"][-1].tool_calls:
                    yield sse("tool", {"name": call["name"], "args": call["args"]})

        answer = to_chat(graph.get_state(config).values["messages"])[-1]
        yield sse("final", answer.model_dump())
    except Exception:
        log.exception("run failed on thread %s", thread_id)
        yield sse("error", {"detail": "Something went wrong on our side, please try again."})

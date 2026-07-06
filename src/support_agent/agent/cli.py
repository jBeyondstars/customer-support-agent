"""Chat with the agent in the terminal, as a given customer.

python -m support_agent.agent.cli --customer 2
"""

import argparse
import uuid

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from support_agent.agent.graph import build_graph
from support_agent.agent.state import Context


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--customer", type=int, required=True, help="customer id (1 to 5 are the demo scenarios)"
    )
    args = parser.parse_args()

    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    context = Context(customer_id=args.customer)

    while True:
        try:
            text = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue

        updates = graph.stream(
            {"messages": [HumanMessage(text)]}, config, context=context, stream_mode="updates"
        )
        for update in updates:
            for node in update.values():
                for message in node["messages"]:
                    if isinstance(message, AIMessage) and message.tool_calls:
                        for call in message.tool_calls:
                            print(f"  [{call['name']}] {call['args']}")
                    elif isinstance(message, AIMessage):
                        print(f"bot> {message.text}")


if __name__ == "__main__":
    main()

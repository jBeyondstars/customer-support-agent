"""Chat with the agent in the terminal, as a given customer.

python -m support_agent.agent.cli --customer 2
"""

import argparse
import uuid

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

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

        run_input = {"messages": [HumanMessage(text)]}
        while run_input is not None:
            pending = None
            for update in graph.stream(run_input, config, context=context, stream_mode="updates"):
                if "__interrupt__" in update:
                    pending = update["__interrupt__"][0].value
                else:
                    print_update(update)

            run_input = None
            if pending:
                for call in pending:
                    print(f"  confirm {call['name']} {call['args']}? [y/N]")
                answer = input("you> ").strip().lower()
                run_input = Command(resume=answer in ("y", "yes", "o", "oui"))


def print_update(update: dict) -> None:
    for node in update.values():
        for message in (node or {}).get("messages", []):
            if isinstance(message, AIMessage) and message.tool_calls:
                for call in message.tool_calls:
                    print(f"  [{call['name']}] {call['args']}")
            elif isinstance(message, AIMessage):
                print(f"bot> {message.text}")


if __name__ == "__main__":
    main()

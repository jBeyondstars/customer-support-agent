from datetime import date
from typing import Literal

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from support_agent.agent.prompts import system_prompt
from support_agent.agent.state import Context
from support_agent.agent.tools import NEEDS_CONFIRMATION, TOOLS
from support_agent.llm import get_chat_model


def agent(state: MessagesState, runtime: Runtime[Context]) -> dict:
    model = get_chat_model().bind_tools(TOOLS)
    # The system prompt isn't stored in the state, so it can change (date, wording)
    # without rewriting old conversations.
    messages = [SystemMessage(system_prompt(date.today())), *state["messages"]]
    return {"messages": [model.invoke(messages)]}


def route_after_agent(state: MessagesState) -> Literal["confirm", "tools", "__end__"]:
    last: AIMessage = state["messages"][-1]
    if not last.tool_calls:
        return END
    if any(call["name"] in NEEDS_CONFIRMATION for call in last.tool_calls):
        return "confirm"
    return "tools"


def confirm(state: MessagesState) -> Command[Literal["tools", "agent"]]:
    calls = state["messages"][-1].tool_calls
    pending = [
        {"name": call["name"], "args": call["args"]}
        for call in calls
        if call["name"] in NEEDS_CONFIRMATION
    ]
    # Pauses the run and saves it in the checkpointer. The value passed to
    # Command(resume=...) comes back here when the customer answers.
    approved = interrupt(pending)
    if approved:
        return Command(goto="tools")

    # Every tool call needs an answer, otherwise the next model call fails.
    declined = [
        ToolMessage("The customer said no, nothing was done.", tool_call_id=call["id"])
        for call in calls
    ]
    return Command(goto="agent", update={"messages": declined})


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    graph = StateGraph(MessagesState, context_schema=Context)
    graph.add_node("agent", agent)
    graph.add_node("confirm", confirm)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent)
    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=checkpointer)

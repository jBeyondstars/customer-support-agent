from datetime import date

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.runtime import Runtime

from support_agent.agent.prompts import system_prompt
from support_agent.agent.state import Context
from support_agent.agent.tools import TOOLS
from support_agent.llm import get_chat_model


def agent(state: MessagesState, runtime: Runtime[Context]) -> dict:
    model = get_chat_model().bind_tools(TOOLS)
    # The system prompt isn't stored in the state, so it can change (date, wording)
    # without rewriting old conversations.
    messages = [SystemMessage(system_prompt(date.today())), *state["messages"]]
    return {"messages": [model.invoke(messages)]}


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    graph = StateGraph(MessagesState, context_schema=Context)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=checkpointer)

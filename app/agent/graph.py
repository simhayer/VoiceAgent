"""LangGraph agent: ReAct-style graph with tool calling."""

import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.prompts import get_system_prompt
from app.agent.state import AgentState
from app.agent.tools import ALL_TOOLS, set_active_db
from app.config import settings

logger = logging.getLogger(__name__)

llm = ChatOpenAI(
    model="gpt-4o",
    api_key=settings.openai_api_key,
    temperature=0.3,
    streaming=False,
)
llm_with_tools = llm.bind_tools(ALL_TOOLS)


async def agent_node(state: AgentState) -> dict:
    """Call the LLM with conversation history and available tools."""
    messages = [SystemMessage(content=get_system_prompt())] + state["messages"]
    response = await llm_with_tools.ainvoke(messages)
    return {"messages": [response]}


async def tool_node(state: AgentState) -> dict:
    """Execute any tool calls from the last AI message."""
    last_message: AIMessage = state["messages"][-1]
    tool_results = []

    tool_map = {t.name: t for t in ALL_TOOLS}

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        logger.info("Executing tool: %s(%s)", tool_name, tool_args)

        tool_fn = tool_map.get(tool_name)
        if tool_fn:
            result = await tool_fn.ainvoke(tool_args)
        else:
            result = f'{{"error": "Unknown tool: {tool_name}"}}'

        tool_results.append(
            ToolMessage(content=str(result), tool_call_id=tool_call["id"])
        )

    return {"messages": tool_results}


def should_continue(state: AgentState) -> str:
    """Route: if the last message has tool calls, go to tools; otherwise end."""
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return END


# Build the graph
graph_builder = StateGraph(AgentState)
graph_builder.add_node("agent", agent_node)
graph_builder.add_node("tools", tool_node)
graph_builder.set_entry_point("agent")
graph_builder.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
graph_builder.add_edge("tools", "agent")

agent_graph = graph_builder.compile()


async def process_message(
    messages: list[dict],
    caller_phone: str,
    db: AsyncSession,
) -> str:
    """Run the agent graph on a conversation and return the final text response.

    This is the main interface called by the voice pipeline.
    """
    set_active_db(db)

    lc_messages = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))

    initial_state: AgentState = {
        "messages": lc_messages,
        "caller_phone": caller_phone,
    }

    result = await agent_graph.ainvoke(initial_state)

    final_messages = result["messages"]
    for msg in reversed(final_messages):
        if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
            return msg.content

    return "I'm sorry, I wasn't able to process that. Could you please repeat?"

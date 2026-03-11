"""LangGraph agent: ReAct-style graph with tool calling and streaming output."""

import logging
import re
import time
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.prompts import get_system_prompt
from app.agent.state import AgentState
from app.agent.tools import ALL_TOOLS, reset_active_db, set_active_db
from app.config import settings

logger = logging.getLogger(__name__)

SENTENCE_BREAK_RE = re.compile(r"[.!?]\s*$")
CLAUSE_BREAK_RE = re.compile(r"[,;:—–]\s*$")
MAX_BUFFER_CHARS = 80
TIME_FLUSH_MIN_CHARS = 24

llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=settings.openai_api_key,
    temperature=0.5,
    streaming=True,
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


graph_builder = StateGraph(AgentState)
graph_builder.add_node("agent", agent_node)
graph_builder.add_node("tools", tool_node)
graph_builder.set_entry_point("agent")
graph_builder.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
graph_builder.add_edge("tools", "agent")

agent_graph = graph_builder.compile()


def _is_flush_point(buffer: str) -> bool:
    """Return True when the buffer ends at a natural speech break."""
    stripped = buffer.strip()
    if not stripped:
        return False
    if SENTENCE_BREAK_RE.search(stripped):
        return True
    if len(stripped) >= MAX_BUFFER_CHARS and CLAUSE_BREAK_RE.search(stripped):
        return True
    return False


def _should_time_flush(buffer: str, last_flush_at: float) -> bool:
    """Fallback flush for long no-punctuation segments."""
    flush_window = settings.agent_stream_flush_ms / 1000
    if flush_window <= 0:
        return False
    stripped = buffer.strip()
    if len(stripped) < TIME_FLUSH_MIN_CHARS:
        return False
    return (time.monotonic() - last_flush_at) >= flush_window


def _build_lc_messages(messages: list[dict]) -> list:
    lc_messages = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
    return lc_messages


async def stream_message(
    messages: list[dict],
    caller_phone: str,
    db: AsyncSession,
) -> AsyncGenerator[tuple[str, str], None]:
    """Stream the agent response as (event_type, data) tuples.

    Yields:
        ("tool_start", tool_name)  — when a tool call begins
        ("text", sentence_fragment) — buffered text at sentence boundaries
    """
    db_token = set_active_db(db)
    try:
        initial_state: AgentState = {
            "messages": _build_lc_messages(messages),
            "caller_phone": caller_phone,
        }

        buffer = ""
        in_tool_phase = False
        last_flush_at = time.monotonic()

        async for event in agent_graph.astream_events(initial_state, version="v2"):
            kind = event["event"]

            if kind == "on_tool_start":
                if buffer.strip():
                    yield ("text", buffer)
                    buffer = ""
                    last_flush_at = time.monotonic()
                in_tool_phase = True
                tool_name = event.get("name", "unknown")
                logger.info("Streaming: tool_start %s", tool_name)
                yield ("tool_start", tool_name)

            elif kind == "on_tool_end":
                in_tool_phase = False
                output = event.get("data", {}).get("output", "")
                if output:
                    truncated = str(output)[:500]
                    yield ("tool_result", truncated)

            elif kind == "on_chat_model_stream" and not in_tool_phase:
                chunk = event["data"].get("chunk")
                if not chunk:
                    continue
                if getattr(chunk, "tool_call_chunks", None) or getattr(chunk, "tool_calls", None):
                    continue
                if hasattr(chunk, "content") and isinstance(chunk.content, str):
                    piece = chunk.content
                    if not piece:
                        continue
                    buffer += piece

                    if _is_flush_point(buffer) or _should_time_flush(buffer, last_flush_at):
                        yield ("text", buffer)
                        buffer = ""
                        last_flush_at = time.monotonic()

        if buffer.strip():
            yield ("text", buffer)
    finally:
        reset_active_db(db_token)


async def process_message(
    messages: list[dict],
    caller_phone: str,
    db: AsyncSession,
) -> str:
    """Non-streaming fallback: run the full graph and return the complete response."""
    db_token = set_active_db(db)
    try:
        initial_state: AgentState = {
            "messages": _build_lc_messages(messages),
            "caller_phone": caller_phone,
        }

        result = await agent_graph.ainvoke(initial_state)

        final_messages = result["messages"]
        for msg in reversed(final_messages):
            if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                return msg.content

        return "I'm sorry, I wasn't able to process that. Could you please repeat?"
    finally:
        reset_active_db(db_token)

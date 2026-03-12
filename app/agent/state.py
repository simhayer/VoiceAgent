"""LangGraph agent state definition."""

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    caller_phone: str
    tenant_id: str
    tenant_name: str
    office_info: dict | None

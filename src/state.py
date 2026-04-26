"""
Conversation state machine for the Payment Collection Agent using LangGraph.
"""

from typing import TypedDict, Optional, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    State schema for the LangGraph agent.
    """
    # Conversation history
    messages: Annotated[list[BaseMessage], add_messages]

    # Session tracking
    session_id: str

    # Account data (from API lookup)
    account_id: Optional[str]
    account_data: Optional[dict]

    # Verification tracking
    provided_name: Optional[str]
    verified: bool
    verification_retries: int

    # Payment tracking
    payment_amount: Optional[float]
    card_details: dict
    payment_retries: int
    transaction_id: Optional[str]

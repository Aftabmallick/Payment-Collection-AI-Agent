"""
Payment Collection AI Agent.
"""

import uuid
import logging
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END

from src.state import AgentState
from src.utils import scrub_pci_from_messages, sanitize_input
from src.nodes import (
    determine_next_node, greeting_and_account, account_lookup,
    collect_name, collect_secondary_factor, payment_decision,
    collect_card_details, process_payment_node, recap_and_close,
    closed_node, checkpointer
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------
builder = StateGraph(AgentState)
nodes = [
    ("greeting_and_account", greeting_and_account),
    ("account_lookup", account_lookup),
    ("collect_name", collect_name),
    ("collect_secondary_factor", collect_secondary_factor),
    ("payment_decision", payment_decision),
    ("collect_card_details", collect_card_details),
    ("process_payment_node", process_payment_node),
    ("recap_and_close", recap_and_close),
    ("closed", closed_node),
]

for name, fn in nodes:
    builder.add_node(name, fn)

builder.add_conditional_edges(START, determine_next_node)

def route_after_node(state: AgentState):
    if state.get("messages") and state["messages"][-1].type == "ai":
        return END
    return determine_next_node(state)

for node in ["greeting_and_account", "account_lookup", "collect_name",
             "collect_secondary_factor", "payment_decision",
             "collect_card_details", "process_payment_node"]:
    builder.add_conditional_edges(node, route_after_node)

builder.add_edge("recap_and_close", END)
builder.add_edge("closed", END)

graph = builder.compile(checkpointer=checkpointer)

# ---------------------------------------------------------------------------
# Session lifecycle management
# ---------------------------------------------------------------------------
_TERMINAL_PHRASES = {"exceeded", "locked", "session has ended", "goodbye", "ended."}

def _is_terminal_message(msg: str) -> bool:
    lower = msg.lower()
    return any(p in lower for p in _TERMINAL_PHRASES)

# ---------------------------------------------------------------------------
# Agent wrapper
# ---------------------------------------------------------------------------
class Agent:
    """
    Agent Class
    """

    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.config = {"configurable": {"thread_id": self.session_id}}
        self._closed = False

        self.state: AgentState = {
            "messages": [], "session_id": self.session_id,
            "account_id": None, "account_data": None,
            "provided_name": None, "verified": False,
            "verification_retries": 0, "payment_amount": None,
            "card_details": {}, "payment_retries": 0,
            "transaction_id": None,
        }

    def next(self, user_input: str) -> dict:
        if self._closed:
            return {"message": "This session has ended. Please start a new session."}

        user_input = sanitize_input(user_input)
        if user_input:
            self.state["messages"].append(HumanMessage(content=user_input))

        try:
            new_state = graph.invoke(self.state, config=self.config)
            self.state = new_state
        except Exception as e:
            logger.error("Graph invocation error: %s", e, exc_info=True)
            return {"message": "I encountered an unexpected error. Please try again."}

        # PCI scrubbing & state cleanup
        if self.state.get("transaction_id") or (
            self.state.get("payment_amount") is not None and self.state["payment_amount"] <= 0
        ):
            self.state["messages"] = scrub_pci_from_messages(self.state["messages"])
            if self.state.get("card_details") and self.state["card_details"].get("card_number"):
                self.state["card_details"] = {
                    "cardholder_name": self.state["card_details"].get("cardholder_name"),
                    "card_last4": self.state["card_details"].get("card_number", "")[-4:],
                }

        if self.state["messages"] and self.state["messages"][-1].type == "ai":
            response = self.state["messages"][-1].content
            if _is_terminal_message(response):
                self._closed = True
            return {"message": response}

        return {"message": "I'm processing your request. Please wait."}

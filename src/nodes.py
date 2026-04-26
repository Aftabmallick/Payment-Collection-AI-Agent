"""
LangGraph nodes and LLM extraction logic for the Payment Collection Agent.
"""

import logging
from typing import Literal, Dict, Any
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage

from src.state import AgentState
from src.tools import lookup_account, process_payment, RETRYABLE_ERRORS
from src.validators import (
    verify_identity, validate_card_number, validate_cvv,
    validate_expiry, validate_amount, parse_date,
)
from src.config import (
    MAX_VERIFICATION_RETRIES, MAX_PAYMENT_RETRIES,
    LLM_MODEL, LLM_TEMPERATURE, LLM_TIMEOUT, LLM_MAX_RETRIES,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MongoDB & Infrastructure (graceful fallback)
# ---------------------------------------------------------------------------
try:
    from pymongo import MongoClient
    from src.config import MONGO_URI, MONGO_DB_NAME
    from src.audit import AuditLogger
    from src.checkpointer import SecureMongoDBSaver
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    mongo_client.admin.command("ping")
    checkpointer = SecureMongoDBSaver(mongo_client, db_name=MONGO_DB_NAME)
    audit_logger = AuditLogger(uri=MONGO_URI, db_name=MONGO_DB_NAME)
    logger.info("MongoDB connected — persistent checkpointer active.")
except Exception:
    from langgraph.checkpoint.memory import MemorySaver
    checkpointer = MemorySaver()
    class _NoOpAuditLogger:
        def log_session_start(self, *a, **kw): pass
        def log_verification_attempt(self, *a, **kw): pass
        def log_payment_attempt(self, *a, **kw): pass
    audit_logger = _NoOpAuditLogger()
    logger.info("MongoDB unavailable — using in-memory checkpointer.")

# ---------------------------------------------------------------------------
# LLM Setup
# ---------------------------------------------------------------------------
llm = ChatOpenAI(
    model=LLM_MODEL, temperature=LLM_TEMPERATURE,
    timeout=LLM_TIMEOUT, max_retries=LLM_MAX_RETRIES,
)

def _safe_llm_extract(extractor, messages, fallback=None):
    try:
        return extractor.invoke(messages)
    except Exception as e:
        logger.error("LLM extraction failed: %s", e, exc_info=True)
        return fallback

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class AccountIDExtraction(BaseModel):
    account_id: str | None = Field(description="The extracted account ID (e.g. ACC1001), or None if not found.")

class NameExtraction(BaseModel):
    name: str | None = Field(description="The user's full name, if clearly provided. None if not.")

class SecondaryFactorExtraction(BaseModel):
    factor_type: Literal["dob", "aadhaar_last4", "pincode"] | None = Field(
        description="Type of secondary factor: dob, aadhaar_last4, or pincode. None if not found.")
    factor_value: str | None = Field(
        description="Raw value of the factor. For dob, standardize to YYYY-MM-DD.")

class PaymentDecision(BaseModel):
    decision: Literal["pay_full", "pay_partial", "decline", "unclear"] = Field(
        description="User's payment intent.")
    amount: float | None = Field(description="Amount if specified, else None.")

class CardDetailsExtraction(BaseModel):
    cardholder_name: str | None = Field(description="Cardholder name")
    card_number: str | None = Field(description="12-16 digit card number, digits only")
    cvv: str | None = Field(description="3 or 4 digit CVV")
    expiry_month: int | None = Field(description="Expiry month (1-12)")
    expiry_year: int | None = Field(description="Expiry year (4 digits)")

# ---------------------------------------------------------------------------
# Node Helpers
# ---------------------------------------------------------------------------
def _last_human_message(state: AgentState) -> str:
    for m in reversed(state.get("messages", [])):
        if m.type == "human":
            return m.content
    return ""

def _recent_human_messages(state: AgentState, n: int = 3) -> list:
    msgs = [m for m in state.get("messages", []) if m.type == "human"]
    return msgs[-n:] if len(msgs) >= n else msgs

_LLM_ERROR_MSG = "I'm having trouble processing your request right now. Could you please try again?"

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def determine_next_node(state: AgentState) -> str:
    if state.get("account_id") is None:
        return "greeting_and_account"
    if state.get("account_data") is None:
        return "account_lookup"
    if not state.get("verified"):
        if state.get("verification_retries", 0) >= MAX_VERIFICATION_RETRIES:
            return "closed"
        if state.get("provided_name") is None:
            return "collect_name"
        return "collect_secondary_factor"
    if state.get("payment_amount") is None:
        return "payment_decision"
    if state.get("payment_amount", 0) <= 0:
        return "closed"
    if state.get("transaction_id"):
        return "recap_and_close"
    cd = state.get("card_details", {})
    if not all(cd.get(k) for k in ("cardholder_name", "card_number", "cvv", "expiry_month")):
        return "collect_card_details"
    return "process_payment_node"

# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def greeting_and_account(state: AgentState) -> Dict[str, Any]:
    last_msg = state["messages"][-1].content if state["messages"] else ""
    if not last_msg:
        return {"messages": [AIMessage(content=(
            "Hello! Welcome to the payment collection service. "
            "I'll help you make a payment on your account today.\n\n"
            "To get started, could you please share your account ID? (e.g., ACC1001)"
        ))]}

    context = _recent_human_messages(state, 3)
    extractor = llm.with_structured_output(AccountIDExtraction)
    result = _safe_llm_extract(extractor, [
        SystemMessage(content="Extract the account ID from the user's message. Account IDs look like ACC followed by numbers (e.g., ACC1001). Return None if not present.")
    ] + context)

    if result and result.account_id:
        logger.info("Account ID extracted: %s", result.account_id)
        audit_logger.log_session_start(state.get("session_id", "unknown"), result.account_id)
        return {"account_id": result.account_id}

    if result is None:
        return {"messages": [AIMessage(content=_LLM_ERROR_MSG)]}

    return {"messages": [AIMessage(content=(
        "I couldn't find a valid account ID in your message. "
        "Account IDs look like ACC1001, ACC1002, etc. Could you please provide your account ID?"
    ))]}


def account_lookup(state: AgentState) -> Dict[str, Any]:
    acc_id = state["account_id"]
    logger.info("Looking up account: %s", acc_id)
    result = lookup_account(acc_id)

    if not result["success"]:
        logger.warning("Account lookup failed: %s", result.get("error"))
        if result.get("error") == "account_not_found":
            return {"account_id": None, "messages": [AIMessage(content=(
                f"No account was found with ID '{acc_id}'. Please double-check your account ID and try again."
            ))]}
        return {"account_id": None, "messages": [AIMessage(content=(
            f"I encountered an issue looking up your account: {result['message']} Please try again."
        ))]}

    logger.info("Account found: %s", acc_id)
    return {"account_data": result["data"]}


def collect_name(state: AgentState) -> Dict[str, Any]:
    last_msg = _last_human_message(state)
    acc_id = state["account_id"]
    ask_msg = (f"Account {acc_id} found. For security purposes, I need to verify your identity "
               "before proceeding.\n\nCould you please provide your full name as registered on the account?")

    if not last_msg:
        return {"messages": [AIMessage(content=ask_msg)]}

    extractor = llm.with_structured_output(NameExtraction)
    result = _safe_llm_extract(extractor, [
        SystemMessage(content=(
            "The user was asked for their full name for identity verification. "
            "Extract the user's full name from their message if they clearly provided it. "
            "Return None if no clear name."
        )),
        HumanMessage(content=last_msg),
    ])

    if result is None:
        return {"messages": [AIMessage(content=_LLM_ERROR_MSG)]}
    if result.name:
        logger.info("Name extracted")
        return {"provided_name": result.name}
    return {"messages": [AIMessage(content=ask_msg)]}


def collect_secondary_factor(state: AgentState) -> Dict[str, Any]:
    last_msg = _last_human_message(state)
    ask_msg = ("Thank you. Now I need to verify one more piece of information.\n\n"
               "Please provide any ONE of the following:\n"
               "- Date of birth\n"
               "- Last 4 digits of your Aadhaar\n"
               "- Pincode")

    extractor = llm.with_structured_output(SecondaryFactorExtraction)
    result = _safe_llm_extract(extractor, [
        SystemMessage(content=(
            "The user was asked for a secondary verification factor. Extract from their message:\n"
            "- dob: date of birth (standardize to YYYY-MM-DD)\n"
            "- aadhaar_last4: last 4 digits of Aadhaar\n"
            "- pincode: 6-digit pincode\n"
            "Return None if not found."
        )),
        HumanMessage(content=last_msg),
    ])

    if result is None:
        return {"messages": [AIMessage(content=_LLM_ERROR_MSG)]}
    if not result.factor_type or not result.factor_value:
        return {"messages": [AIMessage(content=ask_msg)]}

    # Normalize DOB to YYYY-MM-DD for consistent comparison
    factor_value = result.factor_value
    if result.factor_type == "dob" and factor_value:
        normalized = parse_date(factor_value)
        if normalized:
            factor_value = normalized

    is_verified = verify_identity(
        state["account_data"], state["provided_name"],
        result.factor_type, factor_value,
    )
    logger.info("Verification result: %s", is_verified)

    audit_logger.log_verification_attempt(
        state.get("session_id", "unknown"),
        state["account_data"]["account_id"], is_verified, result.factor_type,
    )

    if is_verified:
        balance = state["account_data"].get("balance", 0)
        if balance <= 0:
            return {"verified": True, "payment_amount": 0.0, "messages": [AIMessage(content=(
                "Identity verified successfully!\n\n"
                "Your account has no outstanding balance. There is nothing to pay at this time.\n\n"
                "Thank you for verifying your identity. Have a great day!"
            ))]}
        return {"verified": True, "messages": [AIMessage(content=(
            f"Identity verified successfully!\n\n"
            f"Your outstanding balance is ₹{balance:,.2f}.\n\n"
            "Would you like to make a payment today? You can pay the full amount or a partial amount."
        ))]}

    retries = state.get("verification_retries", 0) + 1
    remaining = MAX_VERIFICATION_RETRIES - retries
    name_matches = state["provided_name"] == state["account_data"].get("full_name", "")
    logger.warning("Verification failed: attempt %d/%d (name_match=%s)", retries, MAX_VERIFICATION_RETRIES, name_matches)

    if remaining <= 0:
        return {"verification_retries": retries, "provided_name": None, "messages": [AIMessage(content=(
            "Verification failed. You have exceeded the maximum number of attempts.\n\n"
            "For your security, this session has been locked. Please contact customer support for assistance."
        ))]}

    if name_matches:
        # Name is correct — only the secondary factor was wrong; don't re-ask for name
        return {"verification_retries": retries, "messages": [AIMessage(content=(
            f"The verification information does not match our records. "
            f"You have {remaining} attempt(s) remaining.\n\n"
            "Please try again with one of the following:\n"
            "- Date of birth (e.g., 1990-05-14)\n"
            "- Last 4 digits of Aadhaar (e.g., 4321)\n"
            "- Pincode (e.g., 400001)"
        ))]}

    # Name didn't match — reset and ask for both
    return {"verification_retries": retries, "provided_name": None, "messages": [AIMessage(content=(
        f"The information you provided does not match our records. "
        f"You have {remaining} attempt(s) remaining.\n\n"
        "Please provide your full name as registered on the account, followed by one of:\n"
        "- Date of birth\n- Last 4 digits of Aadhaar\n- Pincode"
    ))]}


def _process_amount(amount: float, balance: float) -> Dict[str, Any]:
    is_valid, validated_amount, error = validate_amount(str(amount), balance)
    if not is_valid:
        return {"messages": [AIMessage(content=f"{error}\n\nPlease enter a valid amount.")]}
    return {"payment_amount": validated_amount, "card_details": {}, "messages": [AIMessage(content=(
        f"Payment amount: ₹{validated_amount:,.2f}\n\n"
        "Please provide your card details. I'll need:\n"
        "1. Cardholder name\n2. Card number (16 digits)\n"
        "3. CVV (3 or 4 digits)\n4. Expiry date (MM/YYYY)\n\n"
        "You can provide them all at once or one at a time. Let's start — what is the cardholder name?"
    ))]}


def payment_decision(state: AgentState) -> Dict[str, Any]:
    balance = state["account_data"].get("balance", 0)
    context = _recent_human_messages(state, 3)

    extractor = llm.with_structured_output(PaymentDecision)
    result = _safe_llm_extract(extractor, [
        SystemMessage(content=(
            f"The user's outstanding balance is {balance}. Analyze their intent: "
            "'pay_full' = pay entire balance, 'pay_partial' = specific amount, "
            "'decline' = refuse to pay, 'unclear' = can't determine. Extract amount if specified."
        ))
    ] + context)

    if result is None:
        return {"messages": [AIMessage(content=_LLM_ERROR_MSG)]}

    if result.decision == "decline":
        return {"payment_amount": 0.0, "messages": [AIMessage(content=(
            f"No problem. Your outstanding balance remains ₹{balance:,.2f}.\n\n"
            "You can call back anytime to make a payment. Thank you and have a good day!"
        ))]}
    if result.decision == "pay_full":
        return _process_amount(balance, balance)
    if result.amount is not None:
        return _process_amount(result.amount, balance)
    return {"messages": [AIMessage(content=(
        f"Your total outstanding balance is ₹{balance:,.2f}.\n\n"
        "How much would you like to pay? You can pay the full amount or enter a partial amount."
    ))]}


def collect_card_details(state: AgentState) -> Dict[str, Any]:
    current_details = dict(state.get("card_details", {}))
    last_msg = _last_human_message(state)

    # Detect cancel/decline intent before processing card details
    _CANCEL_PHRASES = {"cancel", "stop", "nevermind", "never mind", "don't want", "dont want",
                       "no thanks", "abort", "go back", "decline", "cancel payment", "not now"}
    if last_msg and last_msg.strip().lower() in _CANCEL_PHRASES:
        balance = state["account_data"].get("balance", 0)
        return {"payment_amount": 0.0, "card_details": {}, "messages": [AIMessage(content=(
            f"Payment cancelled. Your outstanding balance remains ₹{balance:,.2f}.\n\n"
            "You can call back anytime to make a payment. Thank you and have a good day!"
        ))]}

    missing = []
    if not current_details.get("cardholder_name"): missing.append("cardholder_name")
    if not current_details.get("card_number"): missing.append("card_number")
    if not current_details.get("cvv"): missing.append("cvv")
    if not current_details.get("expiry_month"): missing.append("expiry_month and expiry_year")

    last_ai_msg = ""
    for m in reversed(state.get("messages", [])):
        if m.type == "ai":
            last_ai_msg = m.content
            break

    extractor = llm.with_structured_output(CardDetailsExtraction)
    result = _safe_llm_extract(extractor, [
        SystemMessage(content=(
            f"The user is providing card payment details. We still need: {', '.join(missing)}. "
            f"The agent's last message was: '{last_ai_msg}'. "
            "Extract ONLY fields clearly present."
        )),
        HumanMessage(content=last_msg),
    ])

    if result is None:
        return {"messages": [AIMessage(content=_LLM_ERROR_MSG)]}

    error_msg = None
    if result:
        if result.cardholder_name and "cardholder_name" not in current_details:
            current_details["cardholder_name"] = result.cardholder_name
        if result.card_number and "card_number" not in current_details:
            is_valid, cleaned = validate_card_number(result.card_number)
            if is_valid: current_details["card_number"] = cleaned
            else: error_msg = f"Invalid card number: {cleaned}\nPlease re-enter."
        if result.cvv and "cvv" not in current_details and not error_msg:
            is_valid, cleaned = validate_cvv(str(result.cvv))
            if is_valid: current_details["cvv"] = cleaned
            else: error_msg = f"Invalid CVV: {cleaned}\nPlease re-enter."
        if result.expiry_month and result.expiry_year and "expiry_month" not in current_details and not error_msg:
            is_valid, err = validate_expiry(result.expiry_month, result.expiry_year)
            if is_valid:
                current_details["expiry_month"] = result.expiry_month
                current_details["expiry_year"] = result.expiry_year
            else: error_msg = f"{err}\nPlease re-enter."

    if error_msg:
        return {"card_details": current_details, "messages": [AIMessage(content=error_msg)]}

    if not current_details.get("cardholder_name"): prompt = "Please provide your cardholder name."
    elif not current_details.get("card_number"): prompt = "Please provide your card number."
    elif not current_details.get("cvv"): prompt = "Please provide your CVV."
    elif not current_details.get("expiry_month"): prompt = "Please provide your card expiry date (MM/YYYY)."
    else: return {"card_details": current_details}

    return {"card_details": current_details, "messages": [AIMessage(content=prompt)]}


def process_payment_node(state: AgentState) -> Dict[str, Any]:
    if state.get("transaction_id"): return {}
    acc_id = state["account_id"]
    amount = state["payment_amount"]
    card_details = state["card_details"]

    logger.info("Processing payment")
    result = process_payment(acc_id, amount, card_details)

    if result["success"]:
        txn_id = result["transaction_id"]
        audit_logger.log_payment_attempt(state.get("session_id", "unknown"), acc_id, amount, True, card_details, transaction_id=txn_id)
        return {"transaction_id": txn_id}

    error_code = result.get("error", "unknown")
    error_msg = result.get("message", "Payment failed.")
    audit_logger.log_payment_attempt(state.get("session_id", "unknown"), acc_id, amount, False, card_details, error_code=error_code)

    if error_code in RETRYABLE_ERRORS:
        retries = state.get("payment_retries", 0) + 1
        remaining = MAX_PAYMENT_RETRIES - retries
        if remaining <= 0:
            return {"payment_retries": retries, "payment_amount": 0.0, "messages": [AIMessage(content=f"Payment failed: {error_msg}\nMax attempts exceeded.")]}
        cd = dict(card_details)
        if error_code == "invalid_card": cd.pop("card_number", None)
        elif error_code == "invalid_cvv": cd.pop("cvv", None)
        elif error_code == "invalid_expiry":
            cd.pop("expiry_month", None)
            cd.pop("expiry_year", None)
        return {"payment_retries": retries, "card_details": cd, "messages": [AIMessage(content=f"Payment failed: {error_msg}\n{remaining} attempts left.")]}

    return {"payment_amount": 0.0, "messages": [AIMessage(content=f"Payment failed: {error_msg}\nTerminal error.")]}


def recap_and_close(state: AgentState) -> Dict[str, Any]:
    acc_id = state["account_id"]
    amount = state["payment_amount"]
    txn_id = state["transaction_id"]
    balance = state["account_data"].get("balance", 0)
    remaining = balance - amount
    return {"messages": [AIMessage(content=(
        f"Payment successful! Here's your summary:\n\n"
        f"  Account: {acc_id}\n  Amount paid: ₹{amount:,.2f}\n"
        f"  Transaction ID: {txn_id}\n  Remaining balance: ₹{remaining:,.2f}\n\n"
        "Please save your transaction ID for your records.\n\n"
        "Thank you for your payment. Have a great day! Goodbye."
    ))]}


def closed_node(state: AgentState) -> Dict[str, Any]:
    return {"messages": [AIMessage(content="This session has ended.")]}

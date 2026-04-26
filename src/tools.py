"""
API tool functions for the Payment Collection Agent.

Wraps the external payment API with:
- Exponential backoff retry for transient failures
- Structured logging for every API call
- Comprehensive error handling and response normalization
"""

import time
import logging
import requests
from src.config import API_BASE_URL, API_TIMEOUT_SECONDS, API_MAX_RETRIES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry decorator (no external dependency)
# ---------------------------------------------------------------------------

_TRANSIENT_ERRORS = (requests.Timeout, requests.ConnectionError)
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504, 429}


def _with_retry(func):
    """Decorator: retry transient HTTP errors with exponential backoff."""
    def wrapper(*args, **kwargs):
        last_exc = None
        for attempt in range(1, API_MAX_RETRIES + 1):
            try:
                result = func(*args, **kwargs)
                # Retry on server-side errors
                if (
                    isinstance(result, dict)
                    and not result.get("success")
                    and result.get("_status_code") in _RETRYABLE_STATUS_CODES
                    and attempt < API_MAX_RETRIES
                ):
                    wait = 2 ** (attempt - 1)
                    logger.warning(
                        "API returned %s, retrying in %ds (attempt %d/%d)",
                        result.get("_status_code"), wait, attempt, API_MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                # Remove internal field before returning
                result.pop("_status_code", None)
                return result
            except _TRANSIENT_ERRORS as exc:
                last_exc = exc
                if attempt < API_MAX_RETRIES:
                    wait = 2 ** (attempt - 1)
                    logger.warning(
                        "API transient error (%s), retrying in %ds (attempt %d/%d)",
                        type(exc).__name__, wait, attempt, API_MAX_RETRIES,
                    )
                    time.sleep(wait)
                else:
                    break

        # All retries exhausted
        if isinstance(last_exc, requests.Timeout):
            return {
                "success": False,
                "error": "timeout",
                "message": "The server took too long to respond after multiple attempts. Please try again later.",
            }
        elif isinstance(last_exc, requests.ConnectionError):
            return {
                "success": False,
                "error": "connection_error",
                "message": "Unable to reach the payment server after multiple attempts. Please check your connection.",
            }
        return {
            "success": False,
            "error": "unexpected_error",
            "message": f"An unexpected error occurred: {last_exc}",
        }

    return wrapper


# ---------------------------------------------------------------------------
# Account Lookup
# ---------------------------------------------------------------------------


@_with_retry
def lookup_account(account_id: str) -> dict:
    """
    Look up an account by ID.

    POST /api/lookup-account

    Returns:
        On success: {"success": True, "data": {account_details}}
        On not found: {"success": False, "error": "account_not_found", "message": "..."}
        On error: {"success": False, "error": "api_error", "message": "..."}
    """
    url = f"{API_BASE_URL}/api/lookup-account"
    payload = {"account_id": account_id}

    logger.info("API call: lookup_account(account_id=%s)", account_id)
    start = time.time()

    try:
        resp = requests.post(url, json=payload, timeout=API_TIMEOUT_SECONDS)
        elapsed = time.time() - start
        logger.info("API response: lookup_account status=%d elapsed=%.2fs", resp.status_code, elapsed)

        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                return {"success": False, "error": "api_error", "message": "Invalid response from server."}
            return {"success": True, "data": data}

        elif resp.status_code == 404:
            try:
                body = resp.json()
                return {
                    "success": False,
                    "error": body.get("error_code", "account_not_found"),
                    "message": body.get("message", "Account not found."),
                }
            except ValueError:
                return {"success": False, "error": "account_not_found", "message": "Account not found."}

        else:
            return {
                "success": False,
                "error": "api_error",
                "message": f"Unexpected response (HTTP {resp.status_code}).",
                "_status_code": resp.status_code,
            }

    except _TRANSIENT_ERRORS:
        raise  # Let the retry decorator handle these
    except Exception as e:
        logger.error("API unexpected error in lookup_account: %s", e, exc_info=True)
        return {
            "success": False,
            "error": "unexpected_error",
            "message": f"An unexpected error occurred: {str(e)}",
        }


# ---------------------------------------------------------------------------
# Process Payment
# ---------------------------------------------------------------------------


@_with_retry
def process_payment(account_id: str, amount: float, card_details: dict) -> dict:
    """
    Process a card payment.

    POST /api/process-payment

    Args:
        account_id: The account to charge against.
        amount: Payment amount (must be > 0, ≤ balance).
        card_details: Dict with keys: cardholder_name, card_number, cvv,
                      expiry_month (int), expiry_year (int).

    Returns:
        On success: {"success": True, "transaction_id": "txn_..."}
        On failure: {"success": False, "error": "error_code", "message": "..."}
    """
    url = f"{API_BASE_URL}/api/process-payment"
    payload = {
        "account_id": account_id,
        "amount": amount,
        "payment_method": {
            "type": "card",
            "card": {
                "cardholder_name": card_details["cardholder_name"],
                "card_number": card_details["card_number"],
                "cvv": card_details["cvv"],
                "expiry_month": card_details["expiry_month"],
                "expiry_year": card_details["expiry_year"],
            },
        },
    }

    # Log WITHOUT card number/CVV
    logger.info(
        "API call: process_payment(account_id=%s, amount=%.2f, card=****%s)",
        account_id, amount, card_details.get("card_number", "")[-4:],
    )
    start = time.time()

    try:
        resp = requests.post(url, json=payload, timeout=API_TIMEOUT_SECONDS)
        elapsed = time.time() - start
        logger.info("API response: process_payment status=%d elapsed=%.2fs", resp.status_code, elapsed)

        if resp.status_code == 200:
            try:
                body = resp.json()
            except ValueError:
                return {"success": False, "error": "api_error", "message": "Invalid response from server."}
            txn_id = body.get("transaction_id", "")
            logger.info("Payment successful: transaction_id=%s", txn_id)
            return {"success": True, "transaction_id": txn_id}

        elif resp.status_code == 422:
            try:
                body = resp.json()
            except ValueError:
                return {"success": False, "error": "api_error", "message": "Payment failed with unknown error."}
            error_code = body.get("error_code", "unknown_error")
            logger.warning("Payment failed: error_code=%s", error_code)
            return {
                "success": False,
                "error": error_code,
                "message": _payment_error_message(error_code),
            }

        else:
            return {
                "success": False,
                "error": "api_error",
                "message": f"Unexpected response (HTTP {resp.status_code}).",
                "_status_code": resp.status_code,
            }

    except _TRANSIENT_ERRORS:
        raise  # Let the retry decorator handle these
    except Exception as e:
        logger.error("API unexpected error in process_payment: %s", e, exc_info=True)
        return {
            "success": False,
            "error": "unexpected_error",
            "message": f"An unexpected error occurred: {str(e)}",
        }


# ---------------------------------------------------------------------------
# Error code → user-friendly message mapping
# ---------------------------------------------------------------------------

_ERROR_MESSAGES = {
    "account_not_found": "The account could not be found. Please verify your account ID.",
    "invalid_amount": "The payment amount is invalid. It must be a positive number with at most 2 decimal places.",
    "insufficient_balance": "The payment amount exceeds the outstanding balance.",
    "invalid_card": "The card number is invalid. Please check and re-enter it.",
    "invalid_cvv": "The CVV is invalid. It should be 3 digits (or 4 for Amex cards).",
    "invalid_expiry": "The card expiry date is invalid or the card has expired.",
}

# Errors that the user can fix by providing new details
RETRYABLE_ERRORS = {"invalid_card", "invalid_cvv", "invalid_expiry", "invalid_amount"}

# Errors that are terminal — cannot be fixed by the user in this session
TERMINAL_ERRORS = {"account_not_found", "insufficient_balance"}


def _payment_error_message(error_code: str) -> str:
    return _ERROR_MESSAGES.get(error_code, f"Payment failed (error: {error_code}).")

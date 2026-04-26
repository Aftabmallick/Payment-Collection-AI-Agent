"""
Input validators and verification logic for the Payment Collection Agent.

All verification is strict — no fuzzy matching, no case-insensitive workarounds.
"""

import re
from datetime import datetime, date


# ---------------------------------------------------------------------------
# Identity Verification
# ---------------------------------------------------------------------------

def verify_identity(account_data: dict, name: str, factor_type: str, factor_value: str) -> bool:
    """
    Verify user identity against account data.

    Requires EXACT name match AND exact match on one secondary factor.
    No fuzzy matching. No case-insensitive comparison.

    Args:
        account_data: Account record from the lookup API.
        name: Full name provided by the user.
        factor_type: One of 'dob', 'aadhaar_last4', 'pincode'.
        factor_value: The value for the secondary factor.

    Returns:
        True if identity is verified, False otherwise.
    """
    # Strict name match (exact, case-sensitive)
    if name != account_data.get("full_name", ""):
        return False

    # Strict secondary factor match
    stored_value = str(account_data.get(factor_type, ""))
    return factor_value == stored_value


# ---------------------------------------------------------------------------
# Date Parsing & Validation
# ---------------------------------------------------------------------------

def parse_date(date_str: str) -> str | None:
    """
    Parse a date string into YYYY-MM-DD format.

    Supports formats: YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, MM/DD/YYYY,
    and natural language like 'May 14, 1990' or '14 May 1990'.

    Returns None if the date is invalid (e.g. Feb 30).
    """
    date_str = date_str.strip()

    # Try ISO format first: YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            return d.isoformat()
        except ValueError:
            return None

    # DD-MM-YYYY or DD/MM/YYYY
    for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
        try:
            d = datetime.strptime(date_str, fmt).date()
            return d.isoformat()
        except ValueError:
            continue

    # Natural language: 'May 14, 1990' or '14 May 1990'
    for fmt in ("%B %d, %Y", "%d %B %Y", "%b %d, %Y", "%d %b %Y"):
        try:
            d = datetime.strptime(date_str, fmt).date()
            return d.isoformat()
        except ValueError:
            continue

    return None


# ---------------------------------------------------------------------------
# Card Validation
# ---------------------------------------------------------------------------

def luhn_check(card_number: str) -> bool:
    """
    Validate a card number using the Luhn algorithm.

    Args:
        card_number: Digits-only card number string.

    Returns:
        True if the card number passes the Luhn check.
    """
    digits = [int(d) for d in card_number]
    digits.reverse()

    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d

    return total % 10 == 0


def validate_card_number(raw: str) -> tuple[bool, str]:
    """
    Validate and normalize a card number.

    Returns:
        (is_valid, cleaned_number_or_error_message)
    """
    # Strip spaces, dashes
    cleaned = re.sub(r"[\s\-]", "", raw.strip())

    if not cleaned.isdigit():
        return False, "Card number must contain only digits."

    if not (12 <= len(cleaned) <= 16):
        return False, f"Card number must be 12-16 digits (got {len(cleaned)})."

    if not luhn_check(cleaned):
        return False, "Card number is invalid (failed checksum)."

    return True, cleaned


def validate_cvv(cvv: str) -> tuple[bool, str]:
    """
    Validate CVV: 3 digits for standard cards, 4 for Amex.

    Returns:
        (is_valid, cleaned_cvv_or_error_message)
    """
    cleaned = cvv.strip()

    if not cleaned.isdigit():
        return False, "CVV must contain only digits."

    if len(cleaned) not in (3, 4):
        return False, f"CVV must be 3 or 4 digits (got {len(cleaned)})."

    return True, cleaned


def validate_expiry(month: int, year: int) -> tuple[bool, str]:
    """
    Validate card expiry: must be a valid month (1-12) and not expired.

    Returns:
        (is_valid, error_message_or_empty)
    """
    if not (1 <= month <= 12):
        return False, f"Expiry month must be 1-12 (got {month})."

    if year < 1000 or year > 9999:
        return False, f"Expiry year must be a 4-digit year (got {year})."

    today = date.today()
    # Card is valid through the last day of the expiry month
    if year < today.year or (year == today.year and month < today.month):
        return False, "This card has expired."

    return True, ""


def parse_expiry(raw: str) -> tuple[int, int] | None:
    """
    Parse expiry from various formats: MM/YY, MM/YYYY, MM-YY, MM-YYYY,
    or separate month/year strings.

    Returns (month, year) or None if unparseable.
    """
    raw = raw.strip()

    # MM/YYYY or MM-YYYY
    m = re.match(r"^(\d{1,2})[/\-](\d{4})$", raw)
    if m:
        return int(m.group(1)), int(m.group(2))

    # MM/YY or MM-YY
    m = re.match(r"^(\d{1,2})[/\-](\d{2})$", raw)
    if m:
        month = int(m.group(1))
        year = 2000 + int(m.group(2))
        return month, year

    return None


# ---------------------------------------------------------------------------
# Amount Validation
# ---------------------------------------------------------------------------

def validate_amount(raw: str, balance: float) -> tuple[bool, float | None, str]:
    """
    Validate a payment amount.

    Rules:
    - Must be a positive number
    - At most 2 decimal places
    - Must be ≤ account balance

    Returns:
        (is_valid, parsed_amount_or_None, error_message_or_empty)
    """
    # Strip currency symbols and commas
    cleaned = re.sub(r"[₹$,\s]", "", raw.strip())

    try:
        amount = float(cleaned)
    except ValueError:
        return False, None, "Please enter a valid number for the amount."

    if amount <= 0:
        return False, None, "Amount must be greater than zero."

    # Check decimal places
    if "." in cleaned:
        decimal_part = cleaned.split(".")[1]
        if len(decimal_part) > 2:
            return False, None, "Amount can have at most 2 decimal places."

    if amount > balance:
        return False, None, (
            f"Amount ₹{amount:,.2f} exceeds the outstanding balance of ₹{balance:,.2f}. "
            f"Please enter an amount up to ₹{balance:,.2f}."
        )

    return True, amount, ""


# ---------------------------------------------------------------------------
# Input Extraction Helpers
# ---------------------------------------------------------------------------

def extract_account_id(text: str) -> str | None:
    """Extract an account ID (e.g., ACC1001) from user input."""
    m = re.search(r"\b(ACC\d{4,})\b", text.upper())
    if m:
        return m.group(1)
    return None


def classify_secondary_factor(text: str) -> tuple[str, str] | None:
    """
    Detect which secondary factor the user is providing and extract the value.

    Returns:
        (factor_type, factor_value) or None if indeterminate.
    """
    lower = text.lower().strip()

    # DOB detection
    dob_patterns = [
        r"(?:dob|date\s*of\s*birth|born|birthday|birth\s*date)\s*(?:is|:|-|—)?\s*(.+)",
        r"(\d{4}-\d{2}-\d{2})",  # ISO date standing alone
        r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",  # DD/MM/YYYY
    ]
    for pattern in dob_patterns:
        m = re.search(pattern, lower)
        if m:
            raw_date = m.group(1).strip()
            parsed = parse_date(raw_date)
            if parsed:
                return "dob", parsed

    # Aadhaar last 4 detection
    aadhaar_patterns = [
        r"(?:aadhaar|aadhar|uidai|uid)\s*(?:last\s*4|last\s*four)?\s*(?:digits?)?\s*(?:is|are|:|-|—)?\s*(\d{4})\b",
        r"(?:last\s*(?:4|four)\s*(?:digits?\s*)?(?:of\s*)?(?:my\s*)?(?:aadhaar|aadhar))\s*(?:is|are|:|-|—)?\s*(\d{4})\b",
    ]
    for pattern in aadhaar_patterns:
        m = re.search(pattern, lower)
        if m:
            return "aadhaar_last4", m.group(1)

    # Pincode detection
    pincode_patterns = [
        r"(?:pin\s*code|pincode|zip|postal)\s*(?:is|:|-|—)?\s*(\d{6})\b",
    ]
    for pattern in pincode_patterns:
        m = re.search(pattern, lower)
        if m:
            return "pincode", m.group(1)

    # If it's just a 6-digit number, likely pincode
    m = re.match(r"^\s*(\d{6})\s*$", text)
    if m:
        return "pincode", m.group(1)

    # If it's just a 4-digit number, likely aadhaar last 4
    m = re.match(r"^\s*(\d{4})\s*$", text)
    if m:
        return "aadhaar_last4", m.group(1)

    # Try parsing the whole thing as a date
    parsed = parse_date(text)
    if parsed:
        return "dob", parsed

    return None

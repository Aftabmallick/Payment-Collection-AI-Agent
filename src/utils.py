"""
Utility functions for the Payment Collection Agent.
"""

import re
import logging
from langchain_core.messages import HumanMessage
from src.config import MAX_INPUT_LENGTH

logger = logging.getLogger(__name__)

# PCI: scrub card numbers and CVVs from message history
_CARD_RE = re.compile(r'\b(\d{4})\s*[-\s]?\s*(\d{4})\s*[-\s]?\s*(\d{4})\s*[-\s]?\s*(\d{1,4})\b')
_LONG_DIGITS_RE = re.compile(r'\b\d{12,19}\b')

def scrub_pci_from_messages(messages: list) -> list:
    """Replace raw card numbers in message history with masked versions."""
    scrubbed = []
    for msg in messages:
        if msg.type == "human":
            content = msg.content
            content = _LONG_DIGITS_RE.sub("[CARD_REDACTED]", content)
            content = _CARD_RE.sub("[CARD_REDACTED]", content)
            scrubbed.append(HumanMessage(content=content, id=getattr(msg, 'id', None)))
        else:
            scrubbed.append(msg)
    return scrubbed

# Input sanitization
_CONTROL_CHARS_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

def sanitize_input(text: str) -> str:
    """Sanitize user input: strip, truncate, remove control chars."""
    text = text.strip()
    text = _CONTROL_CHARS_RE.sub('', text)
    if len(text) > MAX_INPUT_LENGTH:
        text = text[:MAX_INPUT_LENGTH]
        logger.warning("Input truncated to %d chars", MAX_INPUT_LENGTH)
    return text

"""
Configuration constants for the Payment Collection Agent.

All settings can be overridden via environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# API settings
# ---------------------------------------------------------------------------

API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "https://se-payment-verification-api.service.external.usea2.aws.prodigaltech.com",
)
API_TIMEOUT_SECONDS = int(os.getenv("API_TIMEOUT_SECONDS", "15"))
API_MAX_RETRIES = int(os.getenv("API_MAX_RETRIES", "3"))

# ---------------------------------------------------------------------------
# LLM settings
# ---------------------------------------------------------------------------

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

# ---------------------------------------------------------------------------
# Agent settings
# ---------------------------------------------------------------------------

MAX_VERIFICATION_RETRIES = int(os.getenv("MAX_VERIFICATION_RETRIES", "3"))
MAX_PAYMENT_RETRIES = int(os.getenv("MAX_PAYMENT_RETRIES", "3"))
MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "500"))

# Supported secondary verification factors
SECONDARY_FACTORS = ("dob", "aadhaar_last4", "pincode")

# ---------------------------------------------------------------------------
# MongoDB settings (optional)
# ---------------------------------------------------------------------------

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "payment_agent")
AUDIT_COLLECTION = "legal_audits"
CHECKPOINT_COLLECTION = "checkpoints"

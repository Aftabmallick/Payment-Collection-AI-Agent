import datetime
import re
from pymongo import MongoClient
from src.config import MONGO_URI, MONGO_DB_NAME, AUDIT_COLLECTION

class AuditLogger:
    """
    MongoDB Audit Logger for Legal and Compliance tracking.
    """
    def __init__(self, uri=MONGO_URI, db_name=MONGO_DB_NAME, collection_name=AUDIT_COLLECTION):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def _mask_card(self, card_number: str) -> str:
        """Masks a card number, keeping only the last 4 digits."""
        if not card_number:
            return ""
        cleaned = re.sub(r"\D", "", card_number)
        if len(cleaned) < 4:
            return "XXXX"
        return f"XXXX-XXXX-XXXX-{cleaned[-4:]}"

    def log_session_start(self, session_id: str, account_id: str):
        doc = {
            "session_id": session_id,
            "account_id": account_id,
            "event_type": "session_start",
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
        }
        self.collection.insert_one(doc)

    def log_verification_attempt(self, session_id: str, account_id: str, success: bool, factor_type: str):
        doc = {
            "session_id": session_id,
            "account_id": account_id,
            "event_type": "verification_attempt",
            "success": success,
            "factor_type": factor_type,
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
        }
        self.collection.insert_one(doc)

    def log_payment_attempt(self, session_id: str, account_id: str, amount: float, success: bool, card_details: dict, transaction_id: str = None, error_code: str = None):
        # Mask PCI Data before saving
        masked_card = self._mask_card(card_details.get("card_number", ""))
        safe_card_details = {
            "cardholder_name": card_details.get("cardholder_name"),
            "card_number": masked_card,
            "expiry_month": card_details.get("expiry_month"),
            "expiry_year": card_details.get("expiry_year"),
            "cvv_provided": bool(card_details.get("cvv"))
        }

        doc = {
            "session_id": session_id,
            "account_id": account_id,
            "event_type": "payment_attempt",
            "amount": amount,
            "success": success,
            "transaction_id": transaction_id,
            "error_code": error_code,
            "card_details": safe_card_details,
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
        }
        self.collection.insert_one(doc)

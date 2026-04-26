import copy
import re
from langgraph.checkpoint.mongodb import MongoDBSaver

class SecureMongoDBSaver(MongoDBSaver):
    """
    A PCI-compliant LangGraph checkpointer that scrubs sensitive card data
    from the state before persisting it to MongoDB.
    """
    
    def _mask_card(self, card_number: str) -> str:
        if not card_number:
            return ""
        cleaned = re.sub(r"\D", "", card_number)
        if len(cleaned) < 4:
            return "XXXX"
        return f"XXXX-XXXX-XXXX-{cleaned[-4:]}"

    def _scrub_checkpoint(self, checkpoint: dict) -> dict:
        """Deep copy and mask card details in the checkpoint."""
        cp = copy.deepcopy(checkpoint)
        
        # State values are stored in channel_values
        if "channel_values" in cp:
            state = cp["channel_values"]
            if "card_details" in state and isinstance(state["card_details"], dict):
                cd = state["card_details"]
                if cd.get("card_number"):
                    cd["card_number"] = self._mask_card(cd["card_number"])
                if "cvv" in cd:
                    cd["cvv"] = "***"
        return cp

    def put(self, config, checkpoint, metadata, new_versions):
        safe_cp = self._scrub_checkpoint(checkpoint)
        return super().put(config, safe_cp, metadata, new_versions)
        
    async def aput(self, config, checkpoint, metadata, new_versions):
        safe_cp = self._scrub_checkpoint(checkpoint)
        return await super().aput(config, safe_cp, metadata, new_versions)

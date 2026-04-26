import time
from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME, AUDIT_COLLECTION, CHECKPOINT_COLLECTION
from agent import Agent

def run_test():
    print("Starting agent...")
    a = Agent()
    
    # 1. Provide account ID
    res = a.next("My account ID is ACC1001")
    print(res["message"])
    
    # 2. Provide name
    res = a.next("Nithin Jain")
    print(res["message"])
    
    # 3. Provide DOB
    res = a.next("1990-05-14")
    print(res["message"])
    
    # 4. Pay partial
    res = a.next("I want to pay 500")
    print(res["message"])
    
    # 5. Provide card
    res = a.next("Nithin Jain, 4532015112830366, 123, 12/2027")
    print(res["message"])
    
    # 6. Check Mongo
    print("\n--- Checking MongoDB ---")
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    
    audits = list(db[AUDIT_COLLECTION].find({"session_id": a.session_id}))
    print(f"Found {len(audits)} audit records.")
    for au in audits:
        print(f" - {au['event_type']}: {au.get('success', 'N/A')} | Card details: {au.get('card_details', 'N/A')}")
        
    checkpoints = list(db[CHECKPOINT_COLLECTION].find({"thread_id": a.session_id}))
    print(f"Found {len(checkpoints)} checkpoints.")
    
    # Assert card is masked in checkpoint
    for cp in checkpoints:
        if "channel_values" in cp.get("checkpoint", {}):
            cd = cp["checkpoint"]["channel_values"].get("card_details", {})
            if cd.get("card_number"):
                assert "4532" not in cd["card_number"], "Card number not masked in checkpoint!"
                assert "XXXX" in cd["card_number"], "Card number not masked in checkpoint!"
            if "cvv" in cd:
                assert cd["cvv"] == "***", "CVV not masked in checkpoint!"

if __name__ == "__main__":
    run_test()

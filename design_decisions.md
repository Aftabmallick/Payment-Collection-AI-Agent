# 🧠 Design Decisions & Tradeoffs

This document outlines the key technical decisions made during the development of the **Payment Collection AI Agent**, the rationale behind them, and the tradeoffs involved.

## 🏗️ Architecture: LangGraph vs. Simple Loop

### Decision: Use LangGraph (State Machine)
Instead of a simple while-loop or a basic ReAct agent, I chose **LangGraph** to orchestrate the conversation.

**Rationale:**
- **Determinism in Critical Paths**: Financial flows require strict ordering (e.g., verification *before* payment). LangGraph allows us to define "hard" edges and conditional routing logic that forces the agent to follow compliance rules.
- **State Persistence**: LangGraph's built-in checkpointer makes it trivial to save and resume sessions, which is critical for long-running financial conversations.
- **Context Management**: The `AgentState` provides a single source of truth, preventing the agent from "forgetting" verified information.

**Tradeoffs:**
- **Complexity**: LangGraph has a steeper learning curve than simple LangChain scripts.
- **Overhead**: For a very simple 2-turn bot, a graph might be overkill; however, for a production payment system, the robustness justifies the overhead.

---

## 🤖 Verification Logic: LLM-driven Extraction + Rule-based Matching

### Decision: Hybrid Verification
The agent uses the LLM to extract the user's name and secondary factor (DOB, Aadhaar, Pincode) into a structured format, but the **actual comparison** is done using standard Python logic (`src/validators.py`).

**Rationale:**
- **Strictness**: LLMs are prone to "fuzzy" matching or hallucinations. By doing the comparison in code, we ensure 100% exact matching for names and factors as required by the prompt.
- **Security**: Account data (like the correct Aadhaar) is never passed into the LLM prompt. The LLM only sees the *user's input*. The code then compares that input against the API data.

---

## 🔒 Security & PCI Compliance

### Decision: Aggressive State Scrubbing
The `AgentState` is scrubbed of all sensitive card details (CVV, full number) immediately after the payment API call.

**Rationale:**
- **PCI-DSS Compliance**: We must minimize the "attack surface." By scrubbing the state before it hits the MongoDB checkpointer, we ensure that a database breach doesn't leak card numbers.
- **Recap Privacy**: The agent only retains the `card_last4` for the recap message, following industry standards.

---

## 💾 Persistence: MongoDB Integration

### Decision: Multi-tier Persistence
I implemented a `SecureMongoDBSaver` that encrypts/scrubs data before saving, with a graceful fallback to `MemorySaver`.

**Rationale:**
- **Production Readiness**: In-memory storage is fine for testing but fails in distributed environments (like AWS Lambda or Kubernetes). MongoDB provides a scalable persistence layer.
- **Auditability**: The `AuditLogger` provides a separate, append-only record of all critical transitions, which is essential for legal compliance in debt collection.

---

## 🔄 Future Improvements

If I had more time, I would:
1.  **Human-in-the-Loop (HITL)**: Implement a mechanism where the agent can escalate to a human collector if verification fails 3 times, rather than just locking the session.
2.  **Multilingual Support**: Use LLM capabilities to handle payments in Hindi or regional languages while maintaining the same underlying state machine logic.
3.  **Voice Integration**: The current state machine is well-suited for a Voice AI (STT/TTS) implementation.
4.  **Advanced Fraud Detection**: Integrate with external fraud APIs to flag suspicious patterns based on IP, session duration, and payment frequency.

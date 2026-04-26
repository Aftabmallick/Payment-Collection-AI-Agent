# 🧪 Evaluation Approach & Results

This document describes how the **Payment Collection AI Agent** is tested and validated for production readiness.

## 📐 Evaluation Strategy

The evaluation suite (`evaluate.py`) is designed as a **turn-by-turn state-validation framework**. It simulates real user conversations and checks the agent's behavior against expected outcomes at every step.

### Key Metrics
1.  **Success Rate**: Percentage of scenarios where the agent reaches the correct terminal state.
2.  **Correctness of Tool Calls**: Validation that APIs are called only after verification and with correct payloads.
3.  **State Determinism**: Ensuring the agent follows the defined LangGraph nodes consistently.
4.  **Compliance Adherence**: Verifying that no sensitive data (PII/PCI) is exposed in responses.

---

## 🧪 Test Scenarios

The suite covers **17 distinct scenarios** categorized into four groups:

### 1. Happy Paths
- **Full Payment**: End-to-end flow with correct verification and full balance.
- **Partial Payment**: Paying a specific amount less than the balance.
- **Out-of-Order Input**: User provides Account ID in the greeting.

### 2. Failure Handling
- **Verification Failures**: 
    - Wrong Name + Wrong Secondary Factor.
    - Correct Name + Wrong Secondary Factor (verifies retry logic).
    - Session Lockout (after 3 failed attempts).
- **Payment Failures**:
    - Invalid Card Number (Luhn check).
    - Expired Card.
    - Amount Exceeds Balance.

### 3. Edge Cases
- **Leap Year DOB**: Validating `1988-02-29` handling for Rahul Mehta (ACC1004).
- **Zero Balance**: Handling accounts that have nothing to pay (ACC1003).
- **Long Names**: Testing exact matching for Rajarajeswari Balasubramaniam (ACC1002).

### 4. Security & Robustness
- **Sensitive Data Exposure**: Ensuring the agent doesn't reveal "correct" values when a user fails verification.
- **Session Locking**: Ensuring further inputs are rejected after a session is closed.
- **Input Sanitization**: Handling excessively long strings (600+ chars).

---

## 📊 Performance Observations

### Success Rate: 100% (17/17)
The agent currently passes all 17 scenarios in the automated suite.

### Areas of Strength
- **State Persistence**: The transition from `collect_name` to `collect_secondary_factor` is highly reliable.
- **Validation**: The Luhn algorithm and expiry date checks prevent unnecessary API calls.
- **Clarification**: The agent effectively guides users to the next step (e.g., "I still need your CVV").

### Known Limitations
- **Strict Matching**: Because we use exact string matching for names, a typo like "Nithin J" (missing 'ain') will fail verification. 
- **LLM Latency**: Each turn requires an LLM call for extraction, adding ~1-2 seconds of latency per message.

---

## 🚀 Running the Evaluation
To run the full suite:
```bash
python evaluate.py
```
The script will output a turn-by-turn log for each scenario and a final summary report.

# 💳 Payment Collection AI Agent

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![LangChain](https://img.shields.io/badge/LangChain-latest-green.svg)](https://github.com/hwchase17/langchain)
[![LangGraph](https://img.shields.io/badge/LangGraph-latest-orange.svg)](https://github.com/langchain-ai/langgraph)


An enterprise-grade, conversational AI agent designed to handle end-to-end payment collection flows with strict compliance and security standards. Built using **LangGraph**, **LangChain**, and **OpenAI**.

---

## 🌟 Key Features

- **🤖 Intelligent State Machine**: Orchestrated via LangGraph for deterministic yet flexible conversation flows.
- **🛡️ Multi-Factor Identity Verification**: Rigorous account lookup and identity verification (Name + SSN Last 4 or DOB).
- **🔒 PCI-DSS Compliance**: Automated PII/PCI data masking and secure message scrubbing to protect sensitive cardholder information.
- **💾 Session Persistence**: Integration with **MongoDB** for persistent checkpoints and session lifecycle management.
- **⚖️ Legal Audit Logging**: Comprehensive audit trails for all critical actions and transitions.
- **🧪 Robust Evaluation Suite**: Includes a 17-scenario automated test suite to ensure reliability across edge cases.
- **🔄 Fault Tolerance**: Implements exponential backoff for API calls and intelligent retry logic for user verification.

---

## 🛠️ Technology Stack

- **Core Framework**: [LangGraph](https://github.com/langchain-ai/langgraph) & [LangChain](https://github.com/hwchase17/langchain)
- **Intelligence**: [OpenAI GPT-4o](https://openai.com/index/gpt-4o-and-more-capabilities-to-chatgpt/)
- **Database**: [MongoDB](https://www.mongodb.com/) (Checkpoints & Auditing)
- **Language**: Python 3.11+
- **Security**: PII Scrubbing & Input Sanitization

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11 or higher
- MongoDB (Local or Atlas) - *Optional, falls back to in-memory*
- OpenAI API Key

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Aftabmallick/Payment-Collection-AI-Agent.git
   cd Payment-Collection-AI-Agent
   ```

2. **Set up a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   Copy the example environment file and fill in your details.
   ```bash
   cp .env.example .env
   ```
   *Required:* `OPENAI_API_KEY`
   *Optional:* `MONGO_URI` (defaults to `mongodb://localhost:27017/`)

---

## 🎮 Usage

### Running the CLI Agent
Interact with the agent directly in your terminal:
```bash
python cli.py
```

### Running the Evaluation Suite
Validate the agent's behavior against all 17 scenarios:
```bash
python evaluate.py
```

### Database Health Check
Verify your MongoDB connection:
```bash
python test_mongo.py
```

---

## 🏗️ Architecture

The agent follows a strict state machine logic:

1.  **Greeting & Account Lookup**: Identifies the customer via Account ID.
2.  **Identity Verification**: Multi-step verification (Name + Secondary Factor).
3.  **Balance Display**: Presents outstanding balances and payment options.
4.  **Payment Processing**: Securely collects card details and processes transactions via simulated API.
5.  **Recap & Closing**: Provides transaction confirmation and formal closing.

### Security Implementation
- **PCI Scrubbing**: All card numbers are masked (showing only last 4 digits) before state persistence.
- **Input Sanitization**: Prevents injection and handles excessive input lengths.
- **Audit Trails**: Every state transition and API interaction is logged with timestamps and session IDs.

---


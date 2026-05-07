# UnderWrite.AI

**Autonomous AI Underwriting Assistant** — Agentic document analysis for business loan and commercial insurance risk assessment.

---

## Overview

UnderWrite.AI is a portfolio-grade agentic application that demonstrates end-to-end integration of a **ReAct AI Agent**, a **Retrieval-Augmented Generation (RAG) pipeline**, and a **streaming Streamlit frontend**. Users upload a business loan or insurance PDF; the AI agent autonomously parses the document, runs live web reputation checks, cross-references internal policy guidelines, and generates a structured Risk Memo — with no human prompting at any intermediate step.

> Built as a demonstration of agentic workflow architecture, autonomous multi-tool reasoning, and production-quality Python engineering.

---

## Key Technical Features

### Agentic Workflow (Dify.ai)
- **ReAct Agent Node** — Uses function-calling strategy with up to 5 autonomous reasoning iterations. The agent decides *which tools to use*, *in what order*, and *when to stop* — without hard-coded logic
- **Multi-tool Orchestration** — Google Search (web reputation), Dify Knowledge Base (policy compliance RAG), and GPT-4o (synthesis) are invoked dynamically based on document content
- **Decoupled Retrieval & Synthesis** — Follows the Agentic RAG pattern: the agent handles retrieval strategy; a dedicated LLM node handles structured memo generation. This prevents hallucination bleed-through between reasoning and output layers
- **Streaming SSE Pipeline** — The full agent thought-chain and final memo stream back to the frontend via Server-Sent Events in real time

### API Bridge (`dify_client.py`)
- Full **Server-Sent Events** streaming client with per-event-type routing (`agent_thought`, `agent_message`, `message_end`, `error`)
- **Typed exception hierarchy** — `DifyAuthError`, `DifyRateLimitError`, `DifyStreamError` for surgical error handling
- **Automatic retry** via `tenacity` — exponential back-off on 429 rate-limit responses (3 attempts, 2s → 8s)
- **Session management** — `SessionManager` persists `conversation_id` across multi-turn interactions, maintaining agent memory within a session
- Module-level **singleton factory** (`get_client()`) compatible with Streamlit's re-execution model

### PDF Processing (`app.py`)
- **Dual-engine extraction** — `pdfplumber` (primary, handles tables and multi-column layouts) with `PyPDF2` fallback
- Text passed directly to the Dify Chat-Message API as the agent query — no intermediate storage, no data persistence

### Frontend (Streamlit)
- **Live streaming render** — accumulated Markdown memo updates in real time as the agent works
- **Cycling status messages** — 5-stage progress feedback tied to estimated agent reasoning phases
- **Session-scoped state** — UUID-keyed `st.session_state` prevents state bleed across Streamlit reruns
- Download-ready Risk Memo output as `.md`


## Getting Started

### Prerequisites

- Python 3.10+
- A [Dify.ai](https://dify.ai) account (Cloud or self-hosted)
- An OpenAI API key (configured in Dify)
- A SerpAPI key (for Google Search — configured in Dify)

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/underwrite-ai.git
cd underwrite-ai
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```env
DIFY_API_KEY=app-your-key-here
DIFY_BASE_URL=https://api.dify.ai/v1
```

### 4. Import the Dify workflow

1. Log in to your Dify workspace
2. Go to **Studio → Import App**
3. Upload `dify/underwrite_ai_agent.yaml`
4. In the imported app, install the required plugins:
   - `langgenius/openai` — add your OpenAI API key
   - `langgenius/google` — add your SerpAPI key
5. Create a **Knowledge Base** with your underwriting policy documents and replace `REPLACE_WITH_YOUR_DIFY_KNOWLEDGE_BASE_ID` in the YAML with the real KB ID
6. Publish the app and copy the **API Key** from App → API Access into your `.env`

### 5. Run the application

```bash
cd streamlit_app
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501)

### 6. Smoke test the API bridge (optional)

```bash
cd streamlit_app
python dify_client.py
```

---

## How It Works

1. **Upload** — User uploads a business loan or insurance PDF via the Streamlit UI
2. **Extract** — `pdfplumber` extracts the full document text locally (no upload to third-party storage)
3. **Query** — `DifyClient` sends the text to the Dify Chat-Message API with streaming enabled
4. **Retrieve** — The Dify Knowledge Retrieval node pulls relevant policy guidelines from the connected KB
5. **Reason** — The ReAct Agent receives both the document text and the policy context. It autonomously decides to:
   - Run 2-3 targeted Google searches on the applicant entity and key stakeholders
   - Cross-reference findings against retrieved compliance requirements
   - Synthesise risk factors with severity tags (🔴/🟡/🟢)
6. **Synthesise** — A dedicated LLM node reformats the agent's raw findings into a structured 5-section Risk Memo
7. **Stream** — The memo streams back to the UI in real time via SSE. The user sees the agent's reasoning steps and the final memo building live
8. **Download** — The completed memo can be downloaded as a `.md` file
MIT License — see `LICENSE` for details.

---

*UnderWrite.AI is a portfolio project for demonstration purposes. It does not constitute financial, legal, or underwriting advice. All AI-generated outputs require review by a qualified human professional before any action is taken.*

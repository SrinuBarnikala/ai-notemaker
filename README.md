# Personalized Technical Note Maker

> A personalized technical learning and note-making system that understands what the learner already knows, identifies knowledge gaps and misconceptions, and creates a living technical note that evolves with the learner.

---

## Development Status

- **Current Phase:** Phase 8 — Active Recall & Technical Mastery Assessment
- **Status:** Complete (51 tests passing)
- **Features:**
  - Agent 1: Topic Intake & Journey Orchestration
  - Agent 2: Adaptive Knowledge Discovery Probe
  - Agent 3: Mental Model & Knowledge Profile Synthesizer
  - Agent 4: Personalized Architecture Blueprinting
  - Agent 5: Living Structured Note Generator
  - Web Note Viewer: Responsive reader with TOC, Focus Mode, and print-ready styles
  - Living Note Evolution: Interactive section evolution (add code, deepen detail, clarify, add new chapters) with version incrementing (v1 &rarr; v2) and revision history
  - Note Export: Direct GitHub-Flavored Markdown (`.md`) download with frontmatter and structured formatting
  - Agent 6 (Active Recall & Mastery Assessment): Personalized 3D flip flashcards and scenario-based technical quiz with automatic knowledge profile progression (promoting gaps &rarr; mastered)



---

## Project Structure

```text
ai-notemaker/
├── .venv/              # Dedicated local virtual environment (gitignored)
├── backend/            # FastAPI backend application
│   └── app/
│       ├── api/          # REST API endpoints (Journeys, Discovery, Profile, Architecture, Note)
│       ├── architecture/ # Agent 3 — Personalized Note Architecture Agent
│       ├── db/           # SQLite database session and engine setup
│       ├── discovery/    # LangGraph Knowledge Discovery Agent & workflow
│       ├── models/       # SQLAlchemy models (Journey, Interaction, Profile, Concept, Architecture, Note)
│       ├── note/         # Agent 4 — Content Generation Agent (Structured Blocks)
│       ├── profile/      # Agent 2 — Knowledge Profile Agent & synthesis
│       ├── providers/    # LLM provider abstraction (Ollama, OpenAI, Groq, Mock)
│       ├── schemas/      # Pydantic request/response schemas
│       ├── config.py     # Pydantic Settings
│       └── main.py       # FastAPI application and lifespan
├── frontend/           # HTML, CSS, Vanilla JavaScript web UI
│   └── index.html      # Topic Intake, Discovery, Profile Matrix, Architecture, & Living Note Viewer
├── data/               # SQLite database storage (gitignored)
├── tests/              # Unit, API, and provider test suite
├── .env.example        # Configuration template
├── .gitignore          # Git ignore specifications
├── requirements.txt    # Pinned production and test dependencies
└── README.md           # Documentation and status tracker
```

---

## Setup & Running

### 1. Prerequisites
- Python 3.12+
- Git

### 2. Virtual Environment Setup (PowerShell on Windows)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Environment Configuration
```powershell
cp .env.example .env
```

### 4. Running the Application
```powershell
.venv\Scripts\uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

### 5. Running Tests
```powershell
.venv\Scripts\pytest -v tests/
```

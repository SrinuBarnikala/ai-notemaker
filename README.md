# Personalized Technical Note Maker

> A personalized technical learning and note-making system that understands what the learner already knows, identifies knowledge gaps and misconceptions, and creates a living technical note that evolves with the learner.

---

## Development Status

- **Current Phase:** Phase 11 — Socratic AI In-Note Copilot & Semantic Explainer
- **Status:** Complete (64 tests passing)
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
  - Agent 7 (Visual Planner & Architecture Engine): High-clarity Mermaid.js diagrams (flowcharts, sequence, component architecture, state machines, concept maps) with dark-theme rendering, pan/zoom, fullscreen inspection modal, vector SVG download, and on-demand section diagram synthesis
  - Agent 8 (Code Planner & Interactive Code Sandbox): Automatic note-wide code planning, language-specific on-demand section code synthesis (Python, Go, Rust, TypeScript, SQL, Bash), runtime complexity metrics (`O(N)`), test runners, and client-side in-browser WebAssembly Python execution sandbox (Pyodide) with real-time stdout terminal console output
  - Agent 9 (Socratic AI In-Note Copilot & Semantic Explainer): Contextual in-note AI mentor grounded in the learner's knowledge profile and living note context, floating text selection prompt, multi-turn Socratic technical Q&A, targeted follow-up suggestions, and one-click "Pin to Note" direct note augmentation with automatic version bumping and revision logging



---

## Project Structure

```text
ai-notemaker/
├── .venv/              # Dedicated local virtual environment (gitignored)
├── backend/            # FastAPI backend application
│   └── app/
│       ├── api/          # REST API endpoints (Journeys, Discovery, Profile, Architecture, Note, Copilot)
│       ├── architecture/ # Agent 4 — Personalized Note Architecture Agent
│       ├── assessment/   # Agent 6 — Active Recall & Mastery Assessment
│       ├── code/         # Agent 8 — Code Planner & Multi-Language Synthesis
│       ├── copilot/      # Agent 9 — Socratic AI In-Note Copilot & Semantic Explainer
│       ├── db/           # SQLite database session and engine setup
│       ├── discovery/    # Agent 2 — LangGraph Knowledge Discovery Probe
│       ├── models/       # SQLAlchemy models (Journey, Interaction, Profile, Concept, Architecture, Note)
│       ├── note/         # Agent 5 — Content Generation Agent & Evolution Engine
│       ├── profile/      # Agent 3 — Knowledge Profile Synthesizer
│       ├── providers/    # LLM provider abstraction (Ollama, OpenAI, Groq, Mock)
│       ├── schemas/      # Pydantic request/response schemas
│       ├── visuals/      # Agent 7 — Visual Planner & Mermaid Architecture Engine
│       ├── config.py     # Pydantic Settings
│       └── main.py       # FastAPI application and lifespan
├── frontend/           # HTML, CSS, Vanilla JavaScript web UI
│   ├── css/            # Modular stylesheets (main, viewer, modals, components)
│   ├── js/             # Modular domain scripts (state, api, journey, viewer, evolution, assessment, visuals, sandbox, copilot, app)
│   └── index.html      # Clean semantic HTML layout & entrypoint
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

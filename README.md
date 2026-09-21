# Personalized Technical Note Maker

> A personalized technical learning and note-making system that understands what the learner already knows, identifies knowledge gaps and misconceptions, and creates a living technical note that evolves with the learner.

---

## Development Status

- **Current Phase:** Phase 1 — Topic Intake
- **Status:** Complete
- **GitHub Checkpoint:** Pending

---

## Project Structure

```text
ai-notemaker/
├── .venv/              # Dedicated local virtual environment (gitignored)
├── backend/            # FastAPI backend application
│   └── app/
│       ├── api/        # REST API endpoints (Journeys router)
│       ├── db/         # SQLite database session and engine setup
│       ├── models/     # SQLAlchemy ORM models (LearningJourney)
│       ├── providers/  # LLM provider abstraction (Ollama, OpenAI, Groq, Mock)
│       ├── schemas/    # Pydantic request/response schemas
│       ├── config.py   # Pydantic Settings
│       └── main.py     # FastAPI application and lifespan
├── frontend/           # HTML, CSS, Vanilla JavaScript web UI
│   └── index.html      # Topic Intake UI, journey state, and diagnostics
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

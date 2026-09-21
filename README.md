# Personalized Technical Note Maker

> A personalized technical learning and note-making system that understands what the learner already knows, identifies knowledge gaps and misconceptions, and creates a living technical note that evolves with the learner.

---

## Development Status

- **Current Phase:** Phase 0 — Project Foundation
- **Status:** Complete
- **GitHub Checkpoint:** Pending

---

## Project Structure

```text
ai-notemaker/
├── .venv/              # Dedicated local virtual environment (gitignored)
├── backend/            # FastAPI backend application
│   └── app/
│       ├── db/         # SQLite database session and engine setup
│       ├── providers/  # LLM provider abstraction (Ollama, OpenAI, Groq, Mock)
│       ├── config.py   # Pydantic Settings
│       └── main.py     # FastAPI application and health endpoints
├── frontend/           # HTML, CSS, Vanilla JavaScript web UI
│   └── index.html      # Living note viewer and foundation status
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
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy the example environment file:
```powershell
cp .env.example .env
```
Default values use local SQLite and Ollama.

### 4. Running the Application
Start the FastAPI server:
```powershell
.venv\Scripts\uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open your browser at [http://127.0.0.1:8000](http://127.0.0.1:8000) or check the health API at [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health).

### 5. Running Tests
```powershell
.venv\Scripts\pytest -v tests/
```

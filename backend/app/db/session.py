from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.config import get_settings

settings = get_settings()

# Ensure directory for sqlite db exists
if settings.database_url.startswith("sqlite"):
    db_path = settings.database_url.replace("sqlite:///", "")
    if db_path.startswith("./"):
        db_path = db_path[2:]
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    future=True,
)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_health() -> bool:
    """Check whether database connection is active."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            return True
    except Exception:
        return False


def ensure_schema_migrations():
    """Add any missing columns to existing SQLite tables automatically."""
    try:
        with engine.begin() as conn:
            # Check note_revisions columns
            res = conn.execute(text("PRAGMA table_info(note_revisions)")).fetchall()
            cols = [row[1] for row in res]
            if cols:
                if "snapshot" not in cols:
                    conn.execute(text("ALTER TABLE note_revisions ADD COLUMN snapshot TEXT"))
                if "change_summary" not in cols:
                    conn.execute(text("ALTER TABLE note_revisions ADD COLUMN change_summary TEXT"))

            # Check note_architectures columns
            res = conn.execute(text("PRAGMA table_info(note_architectures)")).fetchall()
            cols = [row[1] for row in res]
            if cols:
                if "generation_status" not in cols:
                    conn.execute(text("ALTER TABLE note_architectures ADD COLUMN generation_status VARCHAR(50) DEFAULT 'llm_success'"))
                if "generation_details" not in cols:
                    conn.execute(text("ALTER TABLE note_architectures ADD COLUMN generation_details TEXT"))

            # Check notes columns
            res = conn.execute(text("PRAGMA table_info(notes)")).fetchall()
            cols = [row[1] for row in res]
            if cols:
                if "generation_status" not in cols:
                    conn.execute(text("ALTER TABLE notes ADD COLUMN generation_status VARCHAR(50) DEFAULT 'llm_success'"))
                if "generation_details" not in cols:
                    conn.execute(text("ALTER TABLE notes ADD COLUMN generation_details TEXT"))

            # Check note_sections columns
            res = conn.execute(text("PRAGMA table_info(note_sections)")).fetchall()
            cols = [row[1] for row in res]
            if cols:
                if "generation_status" not in cols:
                    conn.execute(text("ALTER TABLE note_sections ADD COLUMN generation_status VARCHAR(50) DEFAULT 'llm_success'"))
                if "generation_details" not in cols:
                    conn.execute(text("ALTER TABLE note_sections ADD COLUMN generation_details TEXT"))
    except Exception:
        pass


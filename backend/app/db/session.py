import logging
from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.config import get_settings

logger = logging.getLogger(__name__)

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


DISCOVERY_INDEX_NAME = "uq_discovery_journey_question_index"


def _table_columns(conn, table: str) -> list:
    return [row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()]


def ensure_discovery_schema(bind=None) -> dict:
    """
    Additive Knowledge Discovery schema changes. Each step runs in its own transaction, so one
    failure never skips the others, and every failure is logged. Never deletes or rewrites data.
    Returns the outcome per step: "added", "present", "no_table", "skipped_duplicates" or "failed".
    """
    target = bind or engine
    outcome: dict = {}

    def add_column(step: str, table: str, column: str, ddl: str) -> None:
        try:
            with target.begin() as conn:
                cols = _table_columns(conn, table)
                if not cols:
                    outcome[step] = "no_table"
                elif column in cols:
                    outcome[step] = "present"
                else:
                    conn.execute(text(ddl))
                    outcome[step] = "added"
        except Exception:
            outcome[step] = "failed"
            logger.exception("Schema migration step failed: %s", step)

    add_column("discovery_interactions.analysis", "discovery_interactions", "analysis",
               "ALTER TABLE discovery_interactions ADD COLUMN analysis TEXT")
    add_column("knowledge_profiles.learner_context", "knowledge_profiles", "learner_context",
               "ALTER TABLE knowledge_profiles ADD COLUMN learner_context TEXT")

    step = f"index {DISCOVERY_INDEX_NAME}"
    try:
        with target.begin() as conn:
            if not _table_columns(conn, "discovery_interactions"):
                outcome[step] = "no_table"
            elif conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='index' AND name=:n"), {"n": DISCOVERY_INDEX_NAME}
            ).first():
                outcome[step] = "present"
            else:
                duplicates = conn.execute(text(
                    "SELECT journey_id, question_index, COUNT(*) FROM discovery_interactions "
                    "GROUP BY journey_id, question_index HAVING COUNT(*) > 1"
                )).fetchall()
                if duplicates:
                    outcome[step] = "skipped_duplicates"
                    logger.error(
                        "Not creating unique index %s: %d (journey_id, question_index) pair(s) already have "
                        "duplicate rows and NO data was changed. Resolve them manually (for example keep the "
                        "answered row and remove or renumber the other), then restart. Conflicts: %s",
                        DISCOVERY_INDEX_NAME, len(duplicates), [tuple(row) for row in duplicates[:20]],
                    )
                else:
                    conn.execute(text(
                        f"CREATE UNIQUE INDEX IF NOT EXISTS {DISCOVERY_INDEX_NAME} "
                        "ON discovery_interactions (journey_id, question_index)"
                    ))
                    outcome[step] = "added"
    except Exception:
        outcome[step] = "failed"
        logger.exception("Schema migration step failed: %s", step)
    return outcome


def ensure_schema_migrations(bind=None):
    """Add any missing columns to existing SQLite tables automatically."""
    ensure_discovery_schema(bind)
    try:
        with (bind or engine).begin() as conn:
            # Check learning_journeys columns
            res = conn.execute(text("PRAGMA table_info(learning_journeys)")).fetchall()
            cols = [row[1] for row in res]
            if cols:
                if "user_id" not in cols:
                    conn.execute(text("ALTER TABLE learning_journeys ADD COLUMN user_id VARCHAR(36) REFERENCES users(id)"))

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
        logger.exception("Schema auto-migration failed; some columns may be missing.")


import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from backend.app.db.session import SessionLocal, check_db_health, get_db, engine
from backend.app.models.discovery import DiscoveryInteraction


def test_db_health():
    assert check_db_health() is True


def test_db_session():
    db = SessionLocal()
    try:
        assert db is not None
    finally:
        db.close()


def test_get_db_generator():
    gen = get_db()
    db = next(gen)
    assert db is not None
    try:
        next(gen)
    except StopIteration:
        pass


def test_sqlite_foreign_keys_pragma_active():
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA foreign_keys;")).scalar()
        assert result == 1


def test_foreign_key_constraint_enforced():
    db = SessionLocal()
    try:
        invalid_interaction = DiscoveryInteraction(
            journey_id="00000000-0000-0000-0000-000000000000",
            question_index=0,
            question_text="Invalid FK question?",
            concept_target="Testing",
        )
        db.add(invalid_interaction)
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()

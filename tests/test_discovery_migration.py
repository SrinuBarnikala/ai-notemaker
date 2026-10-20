"""Unique-index protection and additive-migration safety. Every database here is a throwaway temp file;
the development database is never opened."""
import logging

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from backend.app.api.discovery import _insert_interaction
from backend.app.db.session import (
    DISCOVERY_INDEX_NAME,
    SessionLocal,
    engine,
    ensure_discovery_schema,
    ensure_schema_migrations,
)
from backend.app.models.discovery import DiscoveryInteraction
from backend.app.models.journey import LearningJourney

INDEX_STEP = f"index {DISCOVERY_INDEX_NAME}"


def make_old_schema(path, *, with_duplicates=False, knowledge_profiles_as_view=False):
    """The schema as it was before the redesign: no analysis / learner_context columns, no unique index."""
    old = create_engine(f"sqlite:///{path.as_posix()}")
    with old.begin() as conn:
        conn.execute(text("CREATE TABLE learning_journeys (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36), topic VARCHAR(500), status VARCHAR(50))"))
        conn.execute(text(
            "CREATE TABLE discovery_interactions (id VARCHAR(36) PRIMARY KEY, journey_id VARCHAR(36), question_index INTEGER, "
            "question_text TEXT, concept_target VARCHAR(200), learner_answer TEXT, quick_assessment TEXT, created_at DATETIME, answered_at DATETIME)"))
        if knowledge_profiles_as_view:
            conn.execute(text("CREATE TABLE kp_source (id VARCHAR(36), journey_id VARCHAR(36), summary TEXT)"))
            conn.execute(text("CREATE VIEW knowledge_profiles AS SELECT id, journey_id, summary FROM kp_source"))
        else:
            conn.execute(text(
                "CREATE TABLE knowledge_profiles (id VARCHAR(36) PRIMARY KEY, journey_id VARCHAR(36), overall_confidence VARCHAR(50), "
                "summary TEXT, misconceptions TEXT, gaps TEXT, created_at DATETIME, updated_at DATETIME)"))
            conn.execute(text("INSERT INTO knowledge_profiles (id, journey_id, summary) VALUES ('p1','j1','Old summary')"))
        conn.execute(text("INSERT INTO learning_journeys VALUES ('j1', NULL, 'Old topic', 'discovery')"))
        conn.execute(text("INSERT INTO learning_journeys VALUES ('j2', NULL, 'Other topic', 'discovery')"))
        conn.execute(text("INSERT INTO discovery_interactions (id, journey_id, question_index, question_text, concept_target, learner_answer) VALUES ('d1','j1',1,'Q1?','T','A1')"))
        conn.execute(text("INSERT INTO discovery_interactions (id, journey_id, question_index, question_text, concept_target) VALUES ('d2','j1',2,'Q2?','T')"))
        conn.execute(text("INSERT INTO discovery_interactions (id, journey_id, question_index, question_text, concept_target) VALUES ('d3','j2',1,'Other Q?','T')"))
        if with_duplicates:
            conn.execute(text("INSERT INTO discovery_interactions (id, journey_id, question_index, question_text, concept_target) VALUES ('d4','j1',2,'Duplicate Q2?','T')"))
    return old


def indexes(eng):
    with eng.connect() as conn:
        return {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))}


def snapshot(eng):
    with eng.connect() as conn:
        return conn.execute(text("SELECT id, journey_id, question_index, question_text, learner_answer FROM discovery_interactions ORDER BY id")).fetchall()


# ---------------------------------------------------------------------------
# Effectiveness
# ---------------------------------------------------------------------------

def test_fresh_databases_enforce_unique_question_numbers():
    assert DISCOVERY_INDEX_NAME in indexes(engine)  # created by create_all from the model
    db = SessionLocal()
    try:
        journey = LearningJourney(topic="Unique index")
        db.add(journey)
        db.commit()
        db.add(DiscoveryInteraction(journey_id=journey.id, question_index=1, question_text="Q?", concept_target="T"))
        db.commit()
        db.add(DiscoveryInteraction(journey_id=journey.id, question_index=1, question_text="Duplicate?", concept_target="T"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        # Same question number in a different journey is fine
        other = LearningJourney(topic="Other")
        db.add(other)
        db.commit()
        db.add(DiscoveryInteraction(journey_id=other.id, question_index=1, question_text="Q?", concept_target="T"))
        db.commit()
    finally:
        db.close()


def test_insert_helper_returns_the_existing_row_instead_of_failing_or_duplicating():
    db = SessionLocal()
    try:
        journey = LearningJourney(topic="Helper")
        db.add(journey)
        db.commit()
        first = _insert_interaction(db, DiscoveryInteraction(
            journey_id=journey.id, question_index=2, question_text="First writer wins?", concept_target="T"))
        second = _insert_interaction(db, DiscoveryInteraction(
            journey_id=journey.id, question_index=2, question_text="Late writer?", concept_target="T"))
        assert second.id == first.id and second.question_text == "First writer wins?"
        assert db.query(DiscoveryInteraction).filter_by(journey_id=journey.id).count() == 1
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Migration of an existing (old-schema) database
# ---------------------------------------------------------------------------

def test_old_database_gets_columns_and_index_without_touching_data(tmp_path):
    old = make_old_schema(tmp_path / "old.db")
    before = snapshot(old)

    outcome = ensure_discovery_schema(old)
    assert outcome == {
        "discovery_interactions.analysis": "added",
        "knowledge_profiles.learner_context": "added",
        INDEX_STEP: "added",
    }
    assert snapshot(old) == before                                   # rows identical
    with old.connect() as conn:
        assert "analysis" in [r[1] for r in conn.execute(text("PRAGMA table_info(discovery_interactions)"))]
        assert conn.execute(text("SELECT analysis FROM discovery_interactions WHERE id='d1'")).scalar() is None
        assert conn.execute(text("SELECT summary, learner_context FROM knowledge_profiles WHERE id='p1'")).one() == ("Old summary", None)
        assert conn.execute(text("PRAGMA integrity_check")).scalar() == "ok"
        assert conn.execute(text("PRAGMA foreign_key_check")).fetchall() == []

    # The index is effective on the migrated database
    with pytest.raises(IntegrityError):
        with old.begin() as conn:
            conn.execute(text("INSERT INTO discovery_interactions (id, journey_id, question_index, question_text, concept_target) VALUES ('x','j1',1,'dup','T')"))


def test_repeated_initialization_is_idempotent(tmp_path):
    old = make_old_schema(tmp_path / "old.db")
    first = ensure_discovery_schema(old)
    again = ensure_discovery_schema(old)
    third = ensure_discovery_schema(old)
    assert first[INDEX_STEP] == "added"
    assert again == third == {
        "discovery_interactions.analysis": "present",
        "knowledge_profiles.learner_context": "present",
        INDEX_STEP: "present",
    }
    ensure_schema_migrations(old)  # the full startup path, twice more, must also be harmless
    ensure_schema_migrations(old)
    assert len(snapshot(old)) == 3


def test_a_database_with_no_discovery_tables_is_left_alone(tmp_path):
    empty = create_engine(f"sqlite:///{(tmp_path / 'empty.db').as_posix()}")
    assert ensure_discovery_schema(empty) == {
        "discovery_interactions.analysis": "no_table",
        "knowledge_profiles.learner_context": "no_table",
        INDEX_STEP: "no_table",
    }


# ---------------------------------------------------------------------------
# Duplicates: report, never rewrite
# ---------------------------------------------------------------------------

def test_existing_duplicates_block_the_index_but_nothing_is_changed_or_deleted(tmp_path, caplog):
    old = make_old_schema(tmp_path / "dups.db", with_duplicates=True)
    before = snapshot(old)

    with caplog.at_level(logging.ERROR, logger="backend.app.db.session"):
        outcome = ensure_discovery_schema(old)

    assert outcome[INDEX_STEP] == "skipped_duplicates"
    assert outcome["discovery_interactions.analysis"] == "added"      # other steps still ran
    assert DISCOVERY_INDEX_NAME not in indexes(old)
    assert snapshot(old) == before                                    # no row deleted, altered or renumbered
    message = " ".join(r.getMessage() for r in caplog.records)
    assert "Not creating unique index" in message and "j1" in message and "NO data was changed" in message

    # Once a person resolves the duplicate, the next start creates the index
    with old.begin() as conn:
        conn.execute(text("DELETE FROM discovery_interactions WHERE id='d4'"))
    assert ensure_discovery_schema(old)[INDEX_STEP] == "added"


# ---------------------------------------------------------------------------
# Errors are surfaced, and one failing step does not skip the others
# ---------------------------------------------------------------------------

def test_a_failing_step_is_logged_and_does_not_skip_the_other_steps(tmp_path, caplog):
    old = make_old_schema(tmp_path / "view.db", knowledge_profiles_as_view=True)  # ALTER TABLE on a view fails
    with caplog.at_level(logging.ERROR, logger="backend.app.db.session"):
        outcome = ensure_discovery_schema(old)

    assert outcome["knowledge_profiles.learner_context"] == "failed"
    assert outcome["discovery_interactions.analysis"] == "added"
    assert outcome[INDEX_STEP] == "added"
    assert any("knowledge_profiles.learner_context" in r.getMessage() and r.exc_info for r in caplog.records)


# ---------------------------------------------------------------------------
# Legacy sessions keep working on the migrated schema
# ---------------------------------------------------------------------------

def test_legacy_rows_are_readable_by_the_orm_after_migration(tmp_path):
    from sqlalchemy.orm import sessionmaker
    old = make_old_schema(tmp_path / "legacy.db")
    ensure_schema_migrations(old)
    session = sessionmaker(bind=old)()
    try:
        rows = session.query(DiscoveryInteraction).order_by(DiscoveryInteraction.id).all()
        assert [r.id for r in rows] == ["d1", "d2", "d3"]
        assert all(r.analysis is None for r in rows)
        assert rows[0].learner_answer == "A1" and rows[1].learner_answer is None
    finally:
        session.close()

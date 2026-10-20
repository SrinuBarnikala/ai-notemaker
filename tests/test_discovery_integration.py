"""Discovery results reaching the profile, architecture and note stages, plus compatibility checks."""
import json
import uuid

from sqlalchemy import create_engine, text

from backend.app.db.session import SessionLocal, engine, ensure_schema_migrations
from backend.app.models.journey import LearningJourney
from backend.app.models.profile import KnowledgeProfile
from backend.app.models.user import User
from backend.app.models.user_profile import UserProfile
from backend.app.personalization.builder import PersonalizationContextBuilder, safe_load_learner_context
from discovery_helpers import finding, opening, profile_json, turn

TOPIC = "Explain Bloom filters"
Q1 = "Why do you think we would want a data structure that sometimes answers 'maybe'?"
ANSWER = "I know hashing basics and want to understand how it works internally well enough to implement it."

RICH_STATE = {
    "understanding": finding("Knows hashing basics", "demonstrated", "I know hashing basics"),
    "intent": finding("Understand the internals well enough to implement it", "stated", "understand how it works internally well enough to implement it"),
    "desired_depth": finding("Internal mechanisms", "inferred"),
    "explanation_preferences": [finding("Likes code examples", "inferred")],
    "challenge_willingness": None,
}


def finished_journey(client, scripted, state=None):
    """Runs discovery to completion in one answer and returns the journey id."""
    scripted.push(opening(Q1), turn(state=state or RICH_STATE, ready=True, finish_reason="Clear goal and level."))
    journey_id = client.post("/journeys", json={"topic": TOPIC}).json()["id"]
    client.post(f"/journeys/{journey_id}/discovery/start")
    res = client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": ANSWER}).json()
    assert res["is_finished"] is True
    return journey_id


# ---------------------------------------------------------------------------
# Learner profile
# ---------------------------------------------------------------------------

def test_profile_keeps_provenance_and_unknowns(client, scripted):
    journey_id = finished_journey(client, scripted)
    scripted.push(profile_json())
    res = client.post(f"/journeys/{journey_id}/knowledge-profile")
    assert res.status_code == 200
    ctx = res.json()["learner_context"]

    assert ctx["original_topic"] == TOPIC
    assert ctx["intention"]["basis"] == "stated"
    assert ctx["intention"]["evidence"] in ANSWER  # a verbatim quote from the learner
    assert ctx["understanding"]["basis"] == "demonstrated"
    assert ctx["desired_depth"]["basis"] == "inferred"  # tentative inference stays labelled as such
    assert ctx["challenge_willingness"] is None          # never established, so unknown
    assert ctx["available_time"] is None
    # Understanding and intention were confirmed by the learner; depth was only inferred, and says so
    assert ctx["unresolved"] == ["Only inferred, not confirmed by the learner: desired depth"]
    assert ctx["discovery"] == {
        "answered_questions": 1, "completed": True, "stopped_reason": "sufficient",
        "fallback_questions": 0, "unanalyzed_answers": 0, "profile_synthesis": "model",
    }

    # The profile model is given the structured state, not just the raw transcript
    profile_prompt = scripted.prompts[-1]
    assert "Understand the internals well enough to implement it [stated]" in profile_prompt
    assert "Willingness to engage with challenging material: unknown" in profile_prompt

    # Retrieval returns exactly what was stored
    assert client.get(f"/journeys/{journey_id}/knowledge-profile").json()["learner_context"] == ctx
    assert client.get(f"/journeys/{journey_id}").json()["status"] == "profile_ready"


def test_profile_with_unusable_model_output_is_flagged_not_invented(client, scripted):
    journey_id = finished_journey(client, scripted)
    res = client.post(f"/journeys/{journey_id}/knowledge-profile")  # queue empty: garbage output
    assert res.status_code == 200
    body = res.json()
    assert body["learner_context"]["discovery"]["profile_synthesis"] == "fallback"
    assert all(c["level"] == "unknown" for c in body["concepts"])
    assert "unavailable" in body["summary"]


def test_profile_provider_failure_is_retryable_and_changes_nothing(client, scripted):
    journey_id = finished_journey(client, scripted)
    scripted.push(RuntimeError("down"))
    res = client.post(f"/journeys/{journey_id}/knowledge-profile")
    assert res.status_code == 503
    assert client.get(f"/journeys/{journey_id}/knowledge-profile").status_code == 404
    assert client.get(f"/journeys/{journey_id}").json()["status"] == "discovery_completed"

    scripted.push(profile_json())
    assert client.post(f"/journeys/{journey_id}/knowledge-profile").status_code == 200


def test_profile_can_be_built_from_a_partial_session(client, scripted):
    """Existing behavior preserved: one answered question is enough, completion is not required."""
    scripted.push(opening(Q1), turn(question="What do you want to build?"), profile_json())
    journey_id = client.post("/journeys", json={"topic": TOPIC}).json()["id"]
    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": ANSWER})
    res = client.post(f"/journeys/{journey_id}/knowledge-profile")
    assert res.status_code == 200
    assert res.json()["learner_context"]["discovery"]["completed"] is False


# ---------------------------------------------------------------------------
# Hand-off to architecture and note generation
# ---------------------------------------------------------------------------

def test_architecture_uses_discovered_intention_and_context(client, scripted):
    journey_id = finished_journey(client, scripted)
    scripted.push(profile_json())
    client.post(f"/journeys/{journey_id}/knowledge-profile")

    res = client.post(f"/journeys/{journey_id}/architecture", json={})
    assert res.status_code == 200
    assert res.json()["learning_goal"] == "Understand the internals well enough to implement it"

    prompt = scripted.prompts[-1]
    assert "Per-topic discovery for THIS topic" in prompt
    assert "Understand the internals well enough to implement it [stated]" in prompt
    assert "Internal mechanisms [inferred]" in prompt


def test_explicit_goal_beats_discovered_goal(client, scripted):
    journey_id = finished_journey(client, scripted)
    scripted.push(profile_json())
    client.post(f"/journeys/{journey_id}/knowledge-profile")
    res = client.post(f"/journeys/{journey_id}/architecture", json={"learning_goal": "Pass my exam"})
    assert res.json()["learning_goal"] == "Pass my exam"


def test_sessions_without_discovered_intention_keep_the_old_default(client, scripted):
    # No intention was ever established (model output unusable), so the previous default applies
    journey_id = client.post("/journeys", json={"topic": TOPIC}).json()["id"]
    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "Not sure."})
    client.post(f"/journeys/{journey_id}/knowledge-profile")
    res = client.post(f"/journeys/{journey_id}/architecture", json={})
    assert res.status_code == 200
    assert res.json()["learning_goal"] == "Master internal mechanics and practical architecture"
    assert "No per-topic discovery details recorded." in scripted.prompts[-1]


def test_note_generation_receives_discovery_context(client, scripted):
    journey_id = finished_journey(client, scripted)
    scripted.push(profile_json())
    client.post(f"/journeys/{journey_id}/knowledge-profile")
    client.post(f"/journeys/{journey_id}/architecture", json={})
    before = scripted.calls
    res = client.post(f"/journeys/{journey_id}/generate-note")
    assert res.status_code == 200
    section_prompts = scripted.prompts[before:]
    assert section_prompts
    assert any("Per-topic discovery (tags" in p and "Likes code examples [inferred]" in p for p in section_prompts)


def test_account_defaults_are_not_overwritten_by_topic_discoveries():
    db = SessionLocal()
    try:
        user = User(id=str(uuid.uuid4()), email=f"u_{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
        db.add(user)
        db.commit()
        db.add(UserProfile(user_id=user.id, explanation_depth="theoretical", learning_style="theory_first"))
        journey = LearningJourney(topic=TOPIC, user_id=user.id)
        db.add(journey)
        db.commit()
        db.add(KnowledgeProfile(
            journey_id=journey.id, summary="Some summary text here.",
            learner_context=json.dumps({
                "intention": finding("Implement it", "stated", "implement"),
                "desired_depth": finding("Quick overview", "stated", "quick"),
                "unresolved": ["Not established: learning intention"],
            }),
        ))
        db.commit()

        ctx = PersonalizationContextBuilder.build(journey.id, db, user_id=user.id)
        assert ctx.explanation_depth == "theoretical"             # account default untouched
        assert ctx.discovered.desired_depth == "Quick overview [stated]"
        assert ctx.discovered_goal == "Implement it"
        assert "Per-topic learner discovery" in ctx.format_for_prompt()

        db.expire_all()
        stored = db.query(UserProfile).filter_by(user_id=user.id).one()
        assert stored.explanation_depth == "theoretical" and stored.learning_style == "theory_first"
    finally:
        db.close()


def test_legacy_profile_without_learner_context_works():
    assert safe_load_learner_context(None) is None
    assert safe_load_learner_context("{not json") is None
    db = SessionLocal()
    try:
        journey = LearningJourney(topic="Legacy")
        db.add(journey)
        db.commit()
        db.add(KnowledgeProfile(journey_id=journey.id, summary="Legacy summary text."))
        db.commit()
        ctx = PersonalizationContextBuilder.build(journey.id, db)
        assert ctx.discovered.is_empty() and ctx.discovered_goal is None
        assert ctx.format_discovery_for_prompt() == "No per-topic discovery details recorded."
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Schema migration and test isolation
# ---------------------------------------------------------------------------

def test_additive_migration_on_old_schema_preserves_data(tmp_path):
    old = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with old.begin() as conn:
        conn.execute(text("CREATE TABLE learning_journeys (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36), topic VARCHAR(500), status VARCHAR(50))"))
        conn.execute(text(
            "CREATE TABLE discovery_interactions (id VARCHAR(36) PRIMARY KEY, journey_id VARCHAR(36), question_index INTEGER, "
            "question_text TEXT, concept_target VARCHAR(200), learner_answer TEXT, quick_assessment TEXT, created_at DATETIME, answered_at DATETIME)"))
        conn.execute(text(
            "CREATE TABLE knowledge_profiles (id VARCHAR(36) PRIMARY KEY, journey_id VARCHAR(36), overall_confidence VARCHAR(50), "
            "summary TEXT, misconceptions TEXT, gaps TEXT, created_at DATETIME, updated_at DATETIME)"))
        conn.execute(text("INSERT INTO learning_journeys VALUES ('j1', NULL, 'Old topic', 'discovery_completed')"))
        conn.execute(text("INSERT INTO discovery_interactions (id, journey_id, question_index, question_text, concept_target, learner_answer) VALUES ('d1','j1',1,'Q?','T','A')"))
        conn.execute(text("INSERT INTO knowledge_profiles (id, journey_id, summary) VALUES ('p1','j1','Old summary')"))

    ensure_schema_migrations(old)
    ensure_schema_migrations(old)  # idempotent

    with old.connect() as conn:
        di_cols = [r[1] for r in conn.execute(text("PRAGMA table_info(discovery_interactions)"))]
        kp_cols = [r[1] for r in conn.execute(text("PRAGMA table_info(knowledge_profiles)"))]
        assert "analysis" in di_cols and "learner_context" in kp_cols
        row = conn.execute(text("SELECT learner_answer, analysis FROM discovery_interactions WHERE id='d1'")).one()
        assert row == ("A", None)
        assert conn.execute(text("SELECT summary, learner_context FROM knowledge_profiles WHERE id='p1'")).one() == ("Old summary", None)


def test_tests_never_use_the_development_database():
    url = str(engine.url).replace("\\", "/")
    assert "notemaker-tests-" in url
    assert "data/app.db" not in url

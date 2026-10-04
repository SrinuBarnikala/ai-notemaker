import json
import uuid
import pytest
from fastapi import HTTPException

from backend.app.models.user import User
from backend.app.models.user_profile import UserProfile
from backend.app.models.journey import LearningJourney
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.models.note import Note
from backend.app.models.assessment import Assessment, AssessmentSubmission
from backend.app.db.session import SessionLocal
from backend.app.personalization.models import (
    PersonalizationContext,
    LearnerProfileContext,
    TopicKnowledgeContext,
    EmpiricalMasteryContext,
    CrossJourneyPriorContext,
)
from backend.app.personalization.builder import (
    PersonalizationContextBuilder,
    JourneyNotFoundError,
    JourneyOwnershipError,
    safe_load_str_list,
)


def test_personalization_context_model_properties_and_prompt_formatting():
    """
    Verifies that the non-persistent PersonalizationContext model correctly calculates
    properties and produces prompt blocks and dictionary context.
    """
    ctx = PersonalizationContext(
        journey_id="j-123",
        topic="Raft Consensus Algorithm",
        journey_status="architecture_ready",
        user_id="user-456",
        learner_profile=LearnerProfileContext(
            experience_level="staff",
            preferred_language="rust",
            secondary_languages=["go", "python"],
            explanation_depth="internals",
            learning_style="practical",
            target_goals="Design high-throughput distributed state machine",
        ),
        topic_knowledge=TopicKnowledgeContext(
            overall_confidence="intermediate",
            mental_model_summary="Understands leader election and RPC heartbeats.",
            known_concepts=["RPC Heartbeats", "Term Numbers"],
            partially_known_concepts=["Log Replication"],
            active_gaps=["Joint Consensus Configuration Changes", "Snapshotting"],
            misconceptions=["Split-brain cannot happen if heartbeats are sent rapidly"],
        ),
        empirical_mastery=EmpiricalMasteryContext(
            verified_mastered_concepts=["RPC Heartbeats", "Election Safety"],
            latest_quiz_score="5/5",
            total_submissions=1,
        ),
        cross_journey=CrossJourneyPriorContext(
            prior_related_concepts=["Paxos Protocols", "Vector Clocks"],
            total_prior_journeys=2,
        ),
    )

    # Flattened properties
    assert ctx.experience_level == "staff"
    assert ctx.preferred_language == "rust"
    assert ctx.secondary_languages == ["go", "python"]
    assert ctx.explanation_depth == "internals"
    assert ctx.learning_style == "practical"
    assert ctx.target_goals == "Design high-throughput distributed state machine"
    assert ctx.overall_confidence == "intermediate"
    assert ctx.known_concepts == ["RPC Heartbeats", "Term Numbers"]
    assert ctx.partially_known_concepts == ["Log Replication"]
    assert ctx.active_gaps == ["Joint Consensus Configuration Changes", "Snapshotting"]
    assert ctx.misconceptions == ["Split-brain cannot happen if heartbeats are sent rapidly"]
    assert ctx.verified_mastered_concepts == ["RPC Heartbeats", "Election Safety"]
    assert ctx.latest_quiz_score == "5/5"
    assert ctx.prior_related_concepts == ["Paxos Protocols", "Vector Clocks"]
    assert ctx.total_prior_journeys == 2

    # Prompt block formatting
    prompt_block = ctx.format_for_prompt()
    assert "=== PERSONALIZED LEARNER CONTEXT ===" in prompt_block
    assert "Topic: Raft Consensus Algorithm" in prompt_block
    assert "Learner Experience Level: Staff" in prompt_block
    assert "Preferred Programming Language: rust" in prompt_block
    assert "Explanation Depth: internals" in prompt_block
    assert "Learning Style: practical" in prompt_block
    assert "Known Concepts (Do not re-explain basic definitions): RPC Heartbeats, Term Numbers" in prompt_block
    assert "Active Knowledge Gaps (Focus deep-dives and clear explanations here): Joint Consensus Configuration Changes, Snapshotting" in prompt_block
    assert "Identified Misconceptions (Debunk or warn against): Split-brain cannot happen if heartbeats are sent rapidly" in prompt_block
    assert "Empirically Verified Mastery (From quizzes): RPC Heartbeats, Election Safety" in prompt_block
    assert "Cross-Journey Prior Knowledge: Paxos Protocols, Vector Clocks" in prompt_block

    # Dict representation
    data_dict = ctx.to_prompt_context()
    assert data_dict["preferred_language"] == "rust"
    assert data_dict["experience_level"] == "staff"
    assert data_dict["latest_quiz_score"] == "5/5"
    assert "formatted_context_block" in data_dict


def test_builder_full_composition_from_db():
    """
    Tests PersonalizationContextBuilder.build() with a complete database learner profile,
    knowledge profile, concepts, assessments, and prior journeys.
    """
    db = SessionLocal()
    try:
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            email=f"builder_user_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password="hashed_test_pass",
        )
        db.add(user)
        db.commit()

        # Custom UserProfile
        profile = UserProfile(
            user_id=user_id,
            display_name="Dev Master",
            experience_level="advanced",
            preferred_language="go",
            secondary_languages=json.dumps(["python", "typescript"]),
            explanation_depth="internals",
            learning_style="practical",
            target_goals="Master concurrency primitives",
        )
        db.add(profile)
        db.commit()

        # Prior Journey 1 (to test cross-journey memory extraction)
        prior_j = LearningJourney(
            topic="Go Goroutines & Channels",
            status="completed",
            user_id=user_id,
        )
        db.add(prior_j)
        db.commit()

        prior_kp = KnowledgeProfile(
            journey_id=prior_j.id,
            overall_confidence="advanced",
            summary="Understands Go channels.",
            misconceptions="[]",
            gaps="[]",
        )
        db.add(prior_kp)
        db.commit()

        c_prior = KnowledgeConcept(
            profile_id=prior_kp.id,
            name="Channel Multiplexing with Select",
            level="strong",
            category="known",
            notes="Channel mechanics",
        )
        db.add(c_prior)
        db.commit()

        # Current Journey 2
        curr_j = LearningJourney(
            topic="Go Memory Model & Sync Primitives",
            status="discovery_completed",
            user_id=user_id,
        )
        db.add(curr_j)
        db.commit()

        curr_kp = KnowledgeProfile(
            journey_id=curr_j.id,
            overall_confidence="intermediate",
            summary="Knows mutex basics, needs deep dive on sync/atomic.",
            misconceptions=json.dumps(["Mutexes are lock-free"]),
            gaps=json.dumps(["Memory Barriers", "Happens-Before Relationship"]),
        )
        db.add(curr_kp)
        db.commit()

        c1 = KnowledgeConcept(
            profile_id=curr_kp.id,
            name="sync.Mutex",
            level="strong",
            category="known",
            notes="Standard locking",
        )
        c2 = KnowledgeConcept(
            profile_id=curr_kp.id,
            name="sync.WaitGroup",
            level="moderate",
            category="partially_known",
            notes="Counter synchronization",
        )
        c3 = KnowledgeConcept(
            profile_id=curr_kp.id,
            name="sync/atomic CAS",
            level="weak",
            category="gap",
            notes="Atomic compare-and-swap",
        )
        db.add_all([c1, c2, c3])
        db.commit()

        # Note for current journey
        note = Note(
            journey_id=curr_j.id,
            topic=curr_j.topic,
            version=1,
            summary="Canonical note for memory model",
        )
        db.add(note)
        db.commit()
        db.refresh(note)

        # Assessment & Submissions for current journey
        assess = Assessment(
            journey_id=curr_j.id,
            note_id=note.id,
            flashcards=json.dumps([{"front": "What is CAS?", "back": "Compare and swap"}]),
            quiz_questions=json.dumps([{"question": "What is mutex?", "explanation": "Lock"}]),
        )
        db.add(assess)
        db.commit()

        sub = AssessmentSubmission(
            assessment_id=assess.id,
            score=4,
            total=5,
            answers=json.dumps({"q1": 0}),
            mastered_concepts=json.dumps(["sync.Mutex"]),
        )
        db.add(sub)
        db.commit()

        # Build context
        context = PersonalizationContextBuilder.build(
            journey_id=curr_j.id,
            db=db,
            user_id=user_id,
        )

        assert context.journey_id == curr_j.id
        assert context.topic == "Go Memory Model & Sync Primitives"
        assert context.user_id == user_id

        # Profile preferences correctly resolved
        assert context.experience_level == "advanced"
        assert context.preferred_language == "go"
        assert context.secondary_languages == ["python", "typescript"]
        assert context.explanation_depth == "internals"
        assert context.learning_style == "practical"

        # Topic knowledge correctly parsed
        assert context.overall_confidence == "intermediate"
        assert "sync.Mutex" in context.known_concepts
        assert "sync.WaitGroup" in context.partially_known_concepts
        assert "sync/atomic CAS" in context.active_gaps
        assert "Memory Barriers" in context.active_gaps
        assert "Happens-Before Relationship" in context.active_gaps
        assert "Mutexes are lock-free" in context.misconceptions

        # Empirical mastery
        assert "sync.Mutex" in context.verified_mastered_concepts
        assert context.latest_quiz_score == "4/5"

        # Cross-journey prior knowledge from earlier journey of this user
        assert "Channel Multiplexing with Select" in context.prior_related_concepts
        assert context.total_prior_journeys == 1

    finally:
        db.close()


def test_builder_strict_journey_ownership_validation():
    """
    Verifies that PersonalizationContextBuilder strictly enforces journey ownership.
    """
    db = SessionLocal()
    try:
        user_a_id = str(uuid.uuid4())
        user_b_id = str(uuid.uuid4())

        user_a = User(
            id=user_a_id,
            email=f"usera_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password="pw",
        )
        user_b = User(
            id=user_b_id,
            email=f"userb_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password="pw",
        )
        db.add_all([user_a, user_b])
        db.commit()

        # Journey owned by User B
        journey_b = LearningJourney(
            topic="Private User B Journey",
            status="created",
            user_id=user_b_id,
        )
        db.add(journey_b)
        db.commit()

        # User A attempting to build context for User B's journey must raise JourneyOwnershipError (403)
        with pytest.raises(JourneyOwnershipError) as exc_info:
            PersonalizationContextBuilder.build(
                journey_id=journey_b.id,
                db=db,
                user_id=user_a_id,
            )
        assert exc_info.value.status_code == 403
        assert "permission" in exc_info.value.detail.lower()

        # Correct owner User B succeeds
        ctx_b = PersonalizationContextBuilder.build(
            journey_id=journey_b.id,
            db=db,
            user_id=user_b_id,
        )
        assert ctx_b.journey_id == journey_b.id

        # Non-existent journey raises JourneyNotFoundError (404)
        with pytest.raises(JourneyNotFoundError) as not_found_info:
            PersonalizationContextBuilder.build(
                journey_id=str(uuid.uuid4()),
                db=db,
                user_id=user_b_id,
            )
        assert not_found_info.value.status_code == 404

        # require_auth_if_owned = True on an owned journey when user_id is None raises 401
        with pytest.raises(HTTPException) as auth_req_info:
            PersonalizationContextBuilder.build(
                journey_id=journey_b.id,
                db=db,
                user_id=None,
                require_auth_if_owned=True,
            )
        assert auth_req_info.value.status_code == 401

    finally:
        db.close()


def test_builder_safe_fallbacks_for_empty_or_corrupted_data():
    """
    Verifies that PersonalizationContextBuilder safely handles missing profiles,
    corrupted JSON fields, and anonymous journeys without crashing.
    """
    db = SessionLocal()
    try:
        # 1. Bare journey with no user, no profile, no assessment
        bare_journey = LearningJourney(
            topic="Bare Bones Topic",
            status="created",
            user_id=None,
        )
        db.add(bare_journey)
        db.commit()

        ctx = PersonalizationContextBuilder.build(journey_id=bare_journey.id, db=db)
        assert ctx.journey_id == bare_journey.id
        assert ctx.topic == "Bare Bones Topic"
        assert ctx.user_id is None

        # Safe defaults for profile
        assert ctx.experience_level == "intermediate"
        assert ctx.preferred_language == "python"
        assert ctx.secondary_languages == []
        assert ctx.explanation_depth == "standard"
        assert ctx.learning_style == "code_and_visual"

        # Safe defaults for knowledge
        assert ctx.overall_confidence == "unknown"
        assert ctx.mental_model_summary == ""
        assert ctx.known_concepts == []
        assert ctx.active_gaps == []
        assert ctx.misconceptions == []

        # Safe defaults for assessment
        assert ctx.verified_mastered_concepts == []
        assert ctx.latest_quiz_score is None

        # Safe defaults for cross-journey
        assert ctx.prior_related_concepts == []
        assert ctx.total_prior_journeys == 0

        # 2. Corrupted JSON fields on KnowledgeProfile
        corrupt_kp = KnowledgeProfile(
            journey_id=bare_journey.id,
            overall_confidence="unknown",
            summary="Fallback summary",
            misconceptions="not a json string at all {corrupted",
            gaps="neither is this [broken",
        )
        db.add(corrupt_kp)
        db.commit()

        ctx_corrupt = PersonalizationContextBuilder.build(journey_id=bare_journey.id, db=db)
        assert ctx_corrupt.overall_confidence == "unknown"
        assert ctx_corrupt.misconceptions == []
        assert ctx_corrupt.active_gaps == []

    finally:
        db.close()


def test_safe_load_str_list_helper():
    """
    Directly verifies safe_load_str_list edge cases.
    """
    assert safe_load_str_list(None) == []
    assert safe_load_str_list("") == []
    assert safe_load_str_list("   ") == []
    assert safe_load_str_list("['foo', 'bar']") == ["foo", "bar"]
    assert safe_load_str_list('["a", "b", "c"]') == ["a", "b", "c"]
    assert safe_load_str_list(["x", "y", "z"]) == ["x", "y", "z"]
    assert safe_load_str_list("comma, separated, items") == ["comma", "separated", "items"]
    assert safe_load_str_list([{"name": "DictConcept"}, {"name": "Other"}]) == ["DictConcept", "Other"]
    assert safe_load_str_list(12345) == []

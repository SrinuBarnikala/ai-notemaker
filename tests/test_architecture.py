import pytest
from backend.app.architecture.parser import parse_note_architecture


def test_architecture_parser_valid_json():
    raw_json = """
    {
      "summary_rationale": "Tailored to address reranking knowledge gap while leveraging solid embedding knowledge.",
      "sections": [
        {
          "order_index": 1,
          "title": "RAG Foundations & Your Starting Mental Model",
          "section_type": "mental_model",
          "depth": "brief",
          "target_concepts": ["Embeddings"],
          "rationale": "Briefly sets the baseline without lecturing on known embeddings.",
          "needs_code": false,
          "needs_visual": true,
          "visual_type": "flowchart"
        },
        {
          "order_index": 2,
          "title": "Deep Dive: Retrieval vs Reranking Mechanics",
          "section_type": "deep_dive",
          "depth": "deep",
          "target_concepts": ["Reranking"],
          "rationale": "Deeply explores why vector similarity is insufficient and how cross-encoders work.",
          "needs_code": true,
          "needs_visual": true,
          "visual_type": "architecture_diagram"
        },
        {
          "order_index": 3,
          "title": "End-to-End Production Pipeline",
          "section_type": "code_walkthrough",
          "depth": "deep",
          "target_concepts": ["Pipeline"],
          "rationale": "Executable FastAPI implementation.",
          "needs_code": true,
          "needs_visual": false,
          "visual_type": null
        }
      ]
    }
    """
    parsed = parse_note_architecture(
        raw_text=raw_json,
        topic="RAG",
        profile_summary="Learner knows embeddings but lacks reranking.",
        concepts=[{"name": "Embeddings", "level": "strong"}],
        gaps=["Reranking"],
        misconceptions=[],
    )
    assert len(parsed.sections) == 3
    assert parsed.sections[0].depth == "brief"
    assert parsed.sections[1].depth == "deep"
    assert parsed.sections[1].needs_code is True
    assert parsed.sections[1].visual_type == "architecture_diagram"


def test_architecture_parser_corrupt_fallback():
    corrupt = "LLM produced random conversation instead of JSON."
    parsed = parse_note_architecture(
        raw_text=corrupt,
        topic="RAG",
        profile_summary="Learner knows embeddings but lacks reranking.",
        concepts=[{"name": "Embeddings", "level": "strong"}],
        gaps=["Reranking Mechanics"],
        misconceptions=["Believes vector search does full reranking"],
    )
    assert len(parsed.sections) >= 4
    # Should include a pitfall/misconception warning section
    assert any(s.section_type == "pitfall_warning" for s in parsed.sections)
    # Should include a deep dive for the gap
    assert any(s.depth == "deep" for s in parsed.sections)


def test_generate_and_get_architecture_flow(client):
    # 1. Create Journey
    j_res = client.post("/journeys", json={"topic": "RAG Architecture"})
    assert j_res.status_code == 201
    journey_id = j_res.json()["id"]

    # 2. Cannot generate architecture before profile exists -> 400
    bad_gen = client.post(f"/journeys/{journey_id}/architecture")
    assert bad_gen.status_code == 400

    # 3. Discovery & Profile setup
    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "I understand embeddings and vector similarity."},
    )
    client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "I have not worked with rerankers or cross-encoders."},
    )
    p_res = client.post(f"/journeys/{journey_id}/knowledge-profile")
    assert p_res.status_code == 200

    # 4. Generate Note Architecture
    arch_res = client.post(
        f"/journeys/{journey_id}/architecture",
        json={"learning_goal": "Build production pipeline with custom reranker"},
    )
    assert arch_res.status_code == 200
    data = arch_res.json()
    assert data["journey_id"] == journey_id
    assert data["topic"] == "RAG Architecture"
    assert len(data["sections"]) >= 3
    assert len(data["summary_rationale"]) > 10

    # Check journey status updated
    j_check = client.get(f"/journeys/{journey_id}")
    assert j_check.json()["status"] == "architecture_ready"

    # 5. Retrieve architecture with GET
    get_res = client.get(f"/journeys/{journey_id}/architecture")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == data["id"]
    assert len(get_res.json()["sections"]) == len(data["sections"])


def test_architecture_unknown_journey(client):
    res = client.get("/journeys/unknown-journey-1234/architecture")
    assert res.status_code == 404


# ==============================================================================
# PHASE 2 PERSONALIZATION CONTEXT INTEGRATION TESTS
# ==============================================================================

import json
import uuid
from unittest.mock import patch

from backend.app.architecture.generator import generate_note_architecture
from backend.app.models.user import User
from backend.app.models.user_profile import UserProfile
from backend.app.models.journey import LearningJourney
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.models.discovery import DiscoveryInteraction
from backend.app.models.note import Note
from backend.app.models.assessment import Assessment, AssessmentSubmission
from backend.app.db.session import SessionLocal
from backend.app.core.security import create_access_token
from backend.app.config import get_settings
from backend.app.providers.mock import MockLLMProvider
from backend.app.personalization.builder import JourneyOwnershipError


@pytest.mark.asyncio
async def test_architecture_prompt_receives_user_profile_preferences():
    """Verify that UserProfile preferences reach the Note Architecture prompt."""
    db = SessionLocal()
    try:
        user = User(
            email=f"arch_pref_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="pw",
        )
        db.add(user)
        db.commit()

        up = UserProfile(
            user_id=user.id,
            experience_level="staff",
            preferred_language="rust",
            explanation_depth="internals",
            learning_style="practical",
            target_goals="Design high-throughput distributed state machine",
        )
        db.add(up)

        journey = LearningJourney(
            user_id=user.id,
            topic="Raft Log Compaction",
            status="profile_created",
        )
        db.add(journey)
        db.commit()

        profile = KnowledgeProfile(
            journey_id=journey.id,
            overall_confidence="intermediate",
            summary="Understands basic log replication but lacks snapshotting mechanics.",
            gaps=json.dumps(["Log Compaction Invariants"]),
            misconceptions=json.dumps(["Heartbeats carry full snapshots"]),
        )
        db.add(profile)
        db.commit()

        mock_provider = MockLLMProvider()
        settings = get_settings()

        with patch("backend.app.architecture.generator.get_llm_provider", return_value=mock_provider):
            res = await generate_note_architecture(
                journey_id=journey.id,
                db=db,
                settings=settings,
                user_id=user.id,
            )

        prompt = mock_provider.last_prompt
        assert "Experience Level: staff" in prompt
        assert "Preferred Programming Language: rust" in prompt
        assert "Explanation Depth Preference: internals" in prompt
        assert "Learning Style: practical" in prompt
        assert "Specific Target Goals: Design high-throughput distributed state machine" in prompt
        assert "Log Compaction Invariants" in prompt
        assert "Heartbeats carry full snapshots" in prompt
        assert res.journey_id == journey.id
    finally:
        db.close()


@pytest.mark.asyncio
async def test_architecture_prompt_receives_mastery_and_cross_journey_concepts():
    """Verify that verified mastery and prior journey concepts reach the prompt."""
    db = SessionLocal()
    try:
        user = User(
            email=f"arch_mastery_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="pw",
        )
        db.add(user)
        db.commit()

        # Prior journey with strong concept to seed cross-journey memory
        prior_j = LearningJourney(
            user_id=user.id,
            topic="Paxos Consensus",
            status="completed",
        )
        db.add(prior_j)
        db.commit()

        prior_kp = KnowledgeProfile(
            journey_id=prior_j.id,
            overall_confidence="advanced",
            summary="Understands Paxos protocol.",
        )
        db.add(prior_kp)
        db.commit()

        c_prior = KnowledgeConcept(
            profile_id=prior_kp.id,
            name="Multi-Paxos Proposer Role",
            level="strong",
            category="known",
            notes="Paxos leadership",
        )
        db.add(c_prior)
        db.commit()

        # Current journey
        curr_j = LearningJourney(
            user_id=user.id,
            topic="Raft Leader Election",
            status="profile_created",
        )
        db.add(curr_j)
        db.commit()

        kp = KnowledgeProfile(
            journey_id=curr_j.id,
            overall_confidence="intermediate",
            summary="Understands randomized election timeouts.",
            gaps=json.dumps(["Split Vote Resolution"]),
            misconceptions=json.dumps([]),
        )
        db.add(kp)
        db.commit()

        # Note for current journey
        note = Note(
            journey_id=curr_j.id,
            topic=curr_j.topic,
            version=1,
            summary="Canonical note for Raft",
        )
        db.add(note)
        db.commit()

        # Assessment with submission on current journey
        assess = Assessment(
            journey_id=curr_j.id,
            note_id=note.id,
        )
        db.add(assess)
        db.commit()

        sub = AssessmentSubmission(
            assessment_id=assess.id,
            score=5,
            total=5,
            mastered_concepts=json.dumps(["Election Safety Guarantee"]),
        )
        db.add(sub)
        db.commit()

        mock_provider = MockLLMProvider()
        settings = get_settings()

        with patch("backend.app.architecture.generator.get_llm_provider", return_value=mock_provider):
            res = await generate_note_architecture(
                journey_id=curr_j.id,
                db=db,
                settings=settings,
                user_id=user.id,
            )

        prompt = mock_provider.last_prompt
        # Empirically verified mastery
        assert "Election Safety Guarantee" in prompt
        # Cross-journey prior concept
        assert "Multi-Paxos Proposer Role" in prompt
        # Active gap
        assert "Split Vote Resolution" in prompt
    finally:
        db.close()


@pytest.mark.asyncio
async def test_architecture_preserves_discovery_summary():
    """Verify that existing DiscoveryInteraction transcript summary is preserved in prompt."""
    db = SessionLocal()
    try:
        journey = LearningJourney(topic="CRDT Mechanics")
        db.add(journey)
        db.commit()

        profile = KnowledgeProfile(
            journey_id=journey.id,
            overall_confidence="beginner",
            summary="New to state-based CRDTs.",
            gaps=json.dumps(["Join Semilattice Convergence"]),
            misconceptions=json.dumps([]),
        )
        db.add(profile)

        disc = DiscoveryInteraction(
            journey_id=journey.id,
            question_index=1,
            question_text="What is your background with distributed state?",
            concept_target="State Convergence",
            learner_answer="I have used event sourcing, but never lattice merges.",
            quick_assessment="Learner knows event sourcing, needs lattice foundations.",
        )
        db.add(disc)
        db.commit()

        mock_provider = MockLLMProvider()
        settings = get_settings()

        with patch("backend.app.architecture.generator.get_llm_provider", return_value=mock_provider):
            await generate_note_architecture(
                journey_id=journey.id,
                db=db,
                settings=settings,
            )

        prompt = mock_provider.last_prompt
        assert "I have used event sourcing, but never lattice merges." in prompt
        assert "Learner knows event sourcing, needs lattice foundations." in prompt
        assert "State Convergence" in prompt
    finally:
        db.close()


@pytest.mark.asyncio
async def test_architecture_missing_learner_data_safe_fallbacks():
    """Verify that empty/missing learner profile and discovery gracefully use safe defaults."""
    db = SessionLocal()
    try:
        journey = LearningJourney(topic="Zero-Copy Networking")
        db.add(journey)
        db.commit()

        profile = KnowledgeProfile(
            journey_id=journey.id,
            overall_confidence="intermediate",
            summary="",
            gaps="[]",
            misconceptions="[]",
        )
        db.add(profile)
        db.commit()

        mock_provider = MockLLMProvider()
        settings = get_settings()

        with patch("backend.app.architecture.generator.get_llm_provider", return_value=mock_provider):
            res = await generate_note_architecture(
                journey_id=journey.id,
                db=db,
                settings=settings,
            )

        prompt = mock_provider.last_prompt
        # Safe defaults should be present
        assert "Experience Level: intermediate" in prompt
        assert "Preferred Programming Language: python" in prompt
        assert "Explanation Depth Preference: standard" in prompt
        assert "Learning Style: code_and_visual" in prompt
        assert "No prior discovery responses recorded." in prompt
        assert res.journey_id == journey.id
        assert len(res.sections) >= 3
    finally:
        db.close()


def test_architecture_cross_user_access_rejected_api(client):
    """Verify that User B cannot generate architecture for a journey owned by User A."""
    db = SessionLocal()
    try:
        user_a = User(email=f"owner_{uuid.uuid4().hex[:8]}@example.com", hashed_password="pw")
        user_b = User(email=f"intruder_{uuid.uuid4().hex[:8]}@example.com", hashed_password="pw")
        db.add(user_a)
        db.add(user_b)
        db.commit()

        journey_a = LearningJourney(user_id=user_a.id, topic="Private Kernel Internals")
        db.add(journey_a)
        db.commit()

        profile_a = KnowledgeProfile(
            journey_id=journey_a.id,
            overall_confidence="advanced",
            summary="Deep Linux kernel knowledge.",
        )
        db.add(profile_a)
        db.commit()

        token_b = create_access_token(subject=user_b.id)

        res = client.post(
            f"/journeys/{journey_a.id}/architecture",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res.status_code == 403
        assert "permission to access learning journey" in res.json()["detail"]
    finally:
        db.close()


def test_architecture_anonymous_journey_still_works_api(client):
    """Verify that anonymous (unauthenticated) journeys generate architecture without error."""
    # 1. Create journey
    j_res = client.post("/journeys", json={"topic": "B-Tree Indexing"})
    assert j_res.status_code == 201
    journey_id = j_res.json()["id"]

    # 2. Run discovery & profile
    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "I know binary search trees and node splitting."},
    )
    p_res = client.post(f"/journeys/{journey_id}/knowledge-profile")
    assert p_res.status_code == 200

    # 3. Generate architecture without authentication
    arch_res = client.post(f"/journeys/{journey_id}/architecture")
    assert arch_res.status_code == 200
    data = arch_res.json()
    assert data["journey_id"] == journey_id
    assert len(data["sections"]) >= 3
    for s in data["sections"]:
        assert s["depth"] in ["brief", "standard", "deep"]
        assert s["section_type"] in ["mental_model", "deep_dive", "bridge", "code_walkthrough", "pitfall_warning"]
        assert isinstance(s["needs_code"], bool)
        assert isinstance(s["needs_visual"], bool)

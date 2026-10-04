import json
import uuid
import pytest
from fastapi.testclient import TestClient

from backend.app.models.user import User
from backend.app.models.journey import LearningJourney
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.models.note import Note, NoteSection
from backend.app.models.assessment import Assessment, AssessmentSubmission
from backend.app.db.session import SessionLocal
from backend.app.memory.memory_service import (
    get_all_concept_memories,
    get_learning_history,
    get_memory_overview,
    get_related_topics,
    get_note_cross_references,
)
from backend.app.memory.search_service import search_knowledge_base


def create_user_and_journey(client, prefix, topic, concepts_data, note_content=""):
    """
    Creates an authenticated user with a journey, knowledge profile, concepts, and note.
    """
    email = f"{prefix}_{uuid.uuid4().hex[:6]}@example.com"
    password = "SecurePassword123!"

    reg_resp = client.post("/auth/register", json={"email": email, "password": password})
    assert reg_resp.status_code == 201

    login_resp = client.post("/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        assert user is not None

        # Create journey owned by this user
        journey = LearningJourney(
            topic=topic,
            status="completed",
            user_id=user.id,
        )
        db.add(journey)
        db.commit()
        db.refresh(journey)

        # Knowledge Profile
        profile = KnowledgeProfile(
            journey_id=journey.id,
            overall_confidence="intermediate",
            summary=f"Understanding of {topic}",
            misconceptions=json.dumps([f"Misconception about {topic}"]),
            gaps=json.dumps([f"Gap in {topic}"]),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        # Concepts
        for c_name, c_cat, c_level in concepts_data:
            c = KnowledgeConcept(
                profile_id=profile.id,
                name=c_name,
                category=c_cat,
                level=c_level,
                notes=f"Notes on {c_name}",
            )
            db.add(c)
        db.commit()

        # Note
        note = Note(
            journey_id=journey.id,
            topic=topic,
            version=1,
            summary=f"Canonical technical note for {topic}",
        )
        db.add(note)
        db.commit()
        db.refresh(note)

        sec = NoteSection(
            note_id=note.id,
            order_index=1,
            title=f"Core Mechanics of {topic}",
            section_type="explanation",
            depth="standard",
            blocks=json.dumps([
                {"type": "paragraph", "content": note_content or f"Discussion of {topic} and concepts."},
            ]),
        )
        db.add(sec)
        db.commit()

        return {
            "user_id": user.id,
            "email": email,
            "headers": headers,
            "journey_id": journey.id,
            "note_id": note.id,
            "topic": topic,
        }
    finally:
        db.close()


def test_concept_memories_strict_user_isolation(client):
    """
    Proves that User A cannot see User B's concept memories via service and API.
    """
    user_a = create_user_and_journey(
        client,
        prefix="usera",
        topic="Distributed Raft Consensus",
        concepts_data=[
            ("Leader Election", "known", "strong"),
            ("Log Replication", "known", "strong"),
            ("Split Brain", "gap", "weak"),
        ],
    )

    user_b = create_user_and_journey(
        client,
        prefix="userb",
        topic="Quantum Cryptography Fundamentals",
        concepts_data=[
            ("Qubits", "known", "strong"),
            ("Quantum Key Distribution", "partially_known", "moderate"),
            ("Shor's Algorithm", "gap", "weak"),
        ],
    )

    db = SessionLocal()
    try:
        # 1. Service Level Verification
        memories_a = get_all_concept_memories(db, user_id=user_a["user_id"])
        memories_b = get_all_concept_memories(db, user_id=user_b["user_id"])

        names_a = [m.concept_name for m in memories_a]
        names_b = [m.concept_name for m in memories_b]

        # User A has Raft concepts, NOT Quantum concepts
        assert "Leader Election" in names_a
        assert "Log Replication" in names_a
        assert "Qubits" not in names_a
        assert "Shor's Algorithm" not in names_a

        # User B has Quantum concepts, NOT Raft concepts
        assert "Qubits" in names_b
        assert "Shor's Algorithm" in names_b
        assert "Leader Election" not in names_b
        assert "Log Replication" not in names_b

        # 2. REST API Level Verification
        res_a = client.get("/memory/concepts", headers=user_a["headers"])
        assert res_a.status_code == 200
        api_names_a = [item["concept_name"] for item in res_a.json()]
        assert "Leader Election" in api_names_a
        assert "Qubits" not in api_names_a

        res_b = client.get("/memory/concepts", headers=user_b["headers"])
        assert res_b.status_code == 200
        api_names_b = [item["concept_name"] for item in res_b.json()]
        assert "Qubits" in api_names_b
        assert "Leader Election" not in api_names_b
    finally:
        db.close()


def test_learning_history_and_overview_user_isolation(client):
    """
    Proves that history and memory overview metrics are strictly isolated between users.
    """
    user_a = create_user_and_journey(
        client,
        prefix="hist_a",
        topic="Compiler Optimization Passes",
        concepts_data=[("Static Single Assignment", "known", "strong")],
    )

    user_b = create_user_and_journey(
        client,
        prefix="hist_b",
        topic="Kubernetes CNI Architecture",
        concepts_data=[("eBPF Data Plane", "known", "strong")],
    )

    # API overview for User A
    res_a = client.get("/memory/overview", headers=user_a["headers"])
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["total_journeys"] == 1
    assert data_a["recent_history"][0]["topic"] == "Compiler Optimization Passes"

    # API overview for User B
    res_b = client.get("/memory/overview", headers=user_b["headers"])
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["total_journeys"] == 1
    assert data_b["recent_history"][0]["topic"] == "Kubernetes CNI Architecture"

    # API history for User A
    hist_a = client.get("/memory/history", headers=user_a["headers"]).json()
    assert len(hist_a) == 1
    assert hist_a[0]["topic"] == "Compiler Optimization Passes"

    # API history for User B
    hist_b = client.get("/memory/history", headers=user_b["headers"]).json()
    assert len(hist_b) == 1
    assert hist_b[0]["topic"] == "Kubernetes CNI Architecture"


def test_cross_user_related_topics_and_cross_references_forbidden(client):
    """
    Proves that User A cannot request related topics or note cross-references for User B's journey.
    """
    user_a = create_user_and_journey(
        client,
        prefix="perm_a",
        topic="Kafka Partitioning Internals",
        concepts_data=[("Consumer Groups", "known", "strong")],
    )

    user_b = create_user_and_journey(
        client,
        prefix="perm_b",
        topic="PostgreSQL WAL Internals",
        concepts_data=[("Write Ahead Log", "known", "strong")],
    )

    # User A requesting related topics for User B's journey -> 403 Forbidden
    res_rel = client.get(f"/memory/related/{user_b['journey_id']}", headers=user_a["headers"])
    assert res_rel.status_code == 403
    assert "permission" in res_rel.json()["detail"].lower()

    # User A requesting cross references for User B's note -> 403 Forbidden
    res_xref = client.get(f"/memory/notes/{user_b['note_id']}/cross-references", headers=user_a["headers"])
    assert res_xref.status_code == 403
    assert "permission" in res_xref.json()["detail"].lower()

    # User A requesting their own journey -> 200 OK
    own_rel = client.get(f"/memory/related/{user_a['journey_id']}", headers=user_a["headers"])
    assert own_rel.status_code == 200

    # User A requesting their own note -> 200 OK
    own_xref = client.get(f"/memory/notes/{user_a['note_id']}/cross-references", headers=user_a["headers"])
    assert own_xref.status_code == 200


def test_search_isolation_across_users(client):
    """
    Proves that searching knowledge base only returns items belonging to the authenticated user.
    """
    user_a = create_user_and_journey(
        client,
        prefix="srch_a",
        topic="UniqueAlphaTopicSecret",
        concepts_data=[("AlphaUniqueConcept", "known", "strong")],
        note_content="UniqueAlpha secret content for notes.",
    )

    user_b = create_user_and_journey(
        client,
        prefix="srch_b",
        topic="UniqueBetaTopicSecret",
        concepts_data=[("BetaUniqueConcept", "known", "strong")],
        note_content="UniqueBeta secret content for notes.",
    )

    # User A searches for Alpha -> Found
    search_a = client.get("/search?q=UniqueAlpha", headers=user_a["headers"]).json()
    assert search_a["total_results"] > 0
    assert any("UniqueAlpha" in str(item) for item in search_a["results"])

    # User A searches for Beta (User B's data) -> 0 results
    search_a_for_b = client.get("/search?q=UniqueBeta", headers=user_a["headers"]).json()
    assert search_a_for_b["total_results"] == 0

    # User B searches for Alpha (User A's data) -> 0 results
    search_b_for_a = client.get("/search?q=UniqueAlpha", headers=user_b["headers"]).json()
    assert search_b_for_a["total_results"] == 0

    # User B searches for Beta -> Found
    search_b = client.get("/search?q=UniqueBeta", headers=user_b["headers"]).json()
    assert search_b["total_results"] > 0
    assert any("UniqueBeta" in str(item) for item in search_b["results"])


def test_graph_isolation_across_users(client):
    """
    Proves that global and journey graphs are scoped and protected against cross-user leakage.
    """
    user_a = create_user_and_journey(
        client,
        prefix="graph_a",
        topic="GraphTopicAlpha",
        concepts_data=[("NodeAlpha", "known", "strong")],
    )

    user_b = create_user_and_journey(
        client,
        prefix="graph_b",
        topic="GraphTopicBeta",
        concepts_data=[("NodeBeta", "known", "strong")],
    )

    # User A requesting User B's journey graph -> 403 Forbidden
    res = client.get(f"/journeys/{user_b['journey_id']}/graph", headers=user_a["headers"])
    assert res.status_code == 403

    # User A global graph -> only contains User A's journey node
    global_a = client.get("/graph/global", headers=user_a["headers"]).json()
    node_names_a = [n["name"] for n in global_a["nodes"]]
    assert "GraphTopicAlpha" in node_names_a
    assert "GraphTopicBeta" not in node_names_a

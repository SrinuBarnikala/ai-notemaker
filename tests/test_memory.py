import json
import pytest
from fastapi.testclient import TestClient

from backend.app.models.journey import LearningJourney
from backend.app.models.profile import KnowledgeProfile, KnowledgeConcept
from backend.app.models.note import Note, NoteSection
from backend.app.models.assessment import Assessment, AssessmentSubmission
from backend.app.db.session import SessionLocal


def seed_test_journeys_and_notes():
    """Helper to populate sample journeys, notes, profiles, and assessments for memory tests."""
    db = SessionLocal()
    try:
        # Journey 1: RAG
        j1 = LearningJourney(topic="RAG Architecture", status="completed")
        db.add(j1)
        db.commit()
        db.refresh(j1)

        # Profile 1
        p1 = KnowledgeProfile(
            journey_id=j1.id,
            overall_confidence="intermediate",
            summary="Solid knowledge of vector embeddings, but has a knowledge gap in cross-encoder reranking.",
            misconceptions=json.dumps(["Cosine similarity is the only way to rank"]),
            gaps=json.dumps(["Reranking algorithms", "BM25 hybrid search"]),
        )
        db.add(p1)
        db.commit()
        db.refresh(p1)

        c1 = KnowledgeConcept(profile_id=p1.id, name="Vector Embeddings", level="strong", category="known", notes="Dense vectors")
        c2 = KnowledgeConcept(profile_id=p1.id, name="Reranking", level="weak", category="gap", notes="Cross-encoder scoring")
        c3 = KnowledgeConcept(profile_id=p1.id, name="Cosine Similarity", level="moderate", category="partially_known", notes="Distance metric")
        db.add_all([c1, c2, c3])
        db.commit()

        # Note 1
        n1 = Note(
            journey_id=j1.id,
            topic="RAG Architecture",
            version=1,
            summary="Complete technical guide to Retrieval Augmented Generation systems.",
        )
        db.add(n1)
        db.commit()
        db.refresh(n1)

        sec1 = NoteSection(
            note_id=n1.id,
            order_index=1,
            title="Vector Retrieval Pipeline",
            section_type="explanation",
            depth="standard",
            blocks=json.dumps([
                {"type": "paragraph", "content": "Vector retrieval searches high-dimensional vector embeddings."},
                {
                    "type": "code",
                    "language": "python",
                    "code": "def rerank_docs(docs, query):\n    return sorted(docs, key=lambda d: d.score, reverse=True)",
                    "explanation": "Simple sorting score for candidate reranking.",
                },
            ]),
        )
        db.add(sec1)
        db.commit()

        # Assessment 1
        a1 = Assessment(
            journey_id=j1.id,
            note_id=n1.id,
            flashcards=json.dumps([
                {"id": "fc1", "front": "What does a cross-encoder do in reranking?", "back": "Scores query-document pairs jointly.", "concept": "Reranking"}
            ]),
            quiz_questions=json.dumps([
                {
                    "id": "q1",
                    "question": "Why is reranking used after initial vector retrieval?",
                    "options": ["To reduce latency", "To achieve higher semantic precision", "To compress embeddings", "To eliminate vectors"],
                    "correct_index": 1,
                    "concept": "Reranking",
                    "explanation": "Rerankers apply compute-heavy models to top-K candidates.",
                }
            ]),
        )
        db.add(a1)
        db.commit()
        db.refresh(a1)

        sub1 = AssessmentSubmission(
            assessment_id=a1.id,
            score=1,
            total=1,
            answers=json.dumps({"q1": 1}),
            mastered_concepts=json.dumps(["Reranking"]),
        )
        db.add(sub1)
        db.commit()

        # Journey 2: Advanced Search (shares Reranking concept)
        j2 = LearningJourney(topic="Hybrid Search & Vector Databases", status="completed")
        db.add(j2)
        db.commit()
        db.refresh(j2)

        p2 = KnowledgeProfile(
            journey_id=j2.id,
            overall_confidence="advanced",
            summary="Mastering hybrid search using BM25 and cross-encoders.",
            misconceptions="[]",
            gaps=json.dumps(["HNSW Indexing"]),
        )
        db.add(p2)
        db.commit()
        db.refresh(p2)

        c4 = KnowledgeConcept(profile_id=p2.id, name="Reranking", level="strong", category="known", notes="Reinforced in hybrid search")
        c5 = KnowledgeConcept(profile_id=p2.id, name="BM25", level="moderate", category="partially_known", notes="Lexical scoring")
        db.add_all([c4, c5])
        db.commit()

        n2 = Note(
            journey_id=j2.id,
            topic="Hybrid Search & Vector Databases",
            version=1,
            summary="A deep dive into combining sparse lexical search with dense vector indexing.",
        )
        db.add(n2)
        db.commit()
        db.refresh(n2)

        sec2 = NoteSection(
            note_id=n2.id,
            order_index=1,
            title="Two-Stage Pipeline with Reranking",
            section_type="explanation",
            depth="deep_dive",
            blocks=json.dumps([
                {"type": "paragraph", "content": "In this two-stage pipeline, candidate results are reranked using cross-encoders."},
                {"type": "definition", "term": "Vector Embeddings", "definition": "High-dimensional geometric representations."},
            ]),
        )
        db.add(sec2)
        db.commit()

        return {
            "j1_id": j1.id,
            "j2_id": j2.id,
            "n1_id": n1.id,
            "n2_id": n2.id,
        }
    finally:
        db.close()


def test_search_endpoint_full_text(client: TestClient):
    data_ids = seed_test_journeys_and_notes()

    # Search for "reranking"
    res = client.get("/search?q=reranking")
    assert res.status_code == 200
    data = res.json()
    assert data["total_results"] > 0
    assert any("rerank" in r["title"].lower() or "rerank" in r["snippet"].lower() for r in data["results"])
    # Check highlight tags
    assert any("<mark>" in r["snippet"] for r in data["results"])


def test_search_filtering_by_type(client: TestClient):
    data_ids = seed_test_journeys_and_notes()

    # Filter by code
    res_code = client.get("/search?q=rerank&type=code")
    assert res_code.status_code == 200
    data_code = res_code.json()
    assert all(r["result_type"] == "code" for r in data_code["results"])
    assert len(data_code["results"]) >= 1

    # Filter by flashcard
    res_fc = client.get("/search?q=cross-encoder&type=flashcard")
    assert res_fc.status_code == 200
    data_fc = res_fc.json()
    assert all(r["result_type"] == "flashcard" for r in data_fc["results"])

    # Search non-existent term
    res_empty = client.get("/search?q=xyznonexistentterm999")
    assert res_empty.status_code == 200
    assert res_empty.json()["total_results"] == 0


def test_concept_memories_and_provenance(client: TestClient):
    data_ids = seed_test_journeys_and_notes()

    # Get all concept memories
    res = client.get("/memory/concepts")
    assert res.status_code == 200
    concepts = res.json()
    assert len(concepts) > 0

    rerank_mem = next((c for c in concepts if c["concept_name"].lower() == "reranking"), None)
    assert rerank_mem is not None
    assert rerank_mem["total_appearances"] >= 2
    assert "RAG Architecture" in rerank_mem["first_encountered_journey_topic"]
    assert "first encountered" in rerank_mem["provenance_story"].lower()

    # Get single concept memory
    res_single = client.get("/memory/concepts/Reranking")
    assert res_single.status_code == 200
    single_data = res_single.json()
    assert single_data["concept_name"].lower() == "reranking"
    assert len(single_data["history"]) >= 2

    # 404 for missing concept
    res_404 = client.get("/memory/concepts/quantum_entanglement_xyz")
    assert res_404.status_code == 404


def test_learning_history_and_overview(client: TestClient):
    data_ids = seed_test_journeys_and_notes()

    # History timeline
    res_hist = client.get("/memory/history")
    assert res_hist.status_code == 200
    hist = res_hist.json()
    assert len(hist) >= 2
    assert any(h["topic"] == "RAG Architecture" for h in hist)

    # Overview stats
    res_ov = client.get("/memory/overview")
    assert res_ov.status_code == 200
    ov = res_ov.json()
    assert ov["total_journeys"] >= 2
    assert ov["total_concepts_tracked"] >= 3
    assert len(ov["top_bridging_concepts"]) >= 1


def test_related_topics_endpoint(client: TestClient):
    data_ids = seed_test_journeys_and_notes()

    res = client.get(f"/memory/related/{data_ids['j1_id']}")
    assert res.status_code == 200
    rel = res.json()
    assert rel["journey_topic"] == "RAG Architecture"
    assert len(rel["related_topics"]) > 0
    # Should recommend next topics or share concepts with Hybrid Search
    assert any("Hybrid Search" in t["topic"] or "Reranking" in t["topic"] or "Vector" in t["topic"] for t in rel["related_topics"])


def test_note_cross_references_in_note_memory(client: TestClient):
    data_ids = seed_test_journeys_and_notes()

    # Note 2 mentions "Vector Embeddings" which was first encountered in Journey 1
    res = client.get(f"/memory/notes/{data_ids['n2_id']}/cross-references")
    assert res.status_code == 200
    data = res.json()
    assert "cross_references" in data
    # At least Vector Embeddings or Reranking was first encountered in Journey 1
    refs = data["cross_references"]
    assert any(r["first_journey_topic"] == "RAG Architecture" for r in refs)


def test_frontend_has_search_and_memory_elements(client: TestClient):
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    # Verify Spotlight search modal & inputs
    assert 'id="spotlight-search-modal"' in html
    assert 'id="spotlight-search-input"' in html
    assert 'id="spotlight-results-container"' in html
    assert 'data-type="code"' in html

    # Verify Knowledge Memory modal & tabs
    assert 'id="knowledge-memory-modal"' in html
    assert 'id="memory-overview-stats"' in html
    assert 'id="btn-mtab-history"' in html
    assert 'id="btn-mtab-concepts"' in html
    assert 'id="btn-mtab-related"' in html

    # Verify Concept Provenance modal
    assert 'id="concept-provenance-modal"' in html
    assert 'id="cprov-title"' in html
    assert 'id="cprov-story"' in html

    # Verify script include
    assert 'src="/static/js/memory.js"' in html

    # Verify header and toolbar search & memory triggers
    assert 'openSearchModal()' in html
    assert 'openMemoryModal(' in html
    assert 'SEARCH &amp; KNOWLEDGE MEMORY' in html
    assert 'PHASE 6' in html



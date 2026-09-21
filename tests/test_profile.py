import pytest
from backend.app.profile.parser import parse_knowledge_profile


def test_profile_parser_valid_json():
    raw_json = """
    {
      "overall_confidence": "intermediate",
      "summary": "Learner understands embeddings and vectors, but has not implemented reranking.",
      "concepts": [
        {"name": "Embeddings", "level": "strong", "category": "known", "notes": "Production ready"},
        {"name": "Reranking", "level": "weak", "category": "unknown", "notes": "No prior usage"}
      ],
      "misconceptions": ["Assumes cosine distance handles reranking automatically"],
      "gaps": ["Cross-encoders", "Retrieval precision metrics"]
    }
    """
    parsed = parse_knowledge_profile(raw_json, topic="RAG", interactions=[])
    assert parsed.overall_confidence == "intermediate"
    assert len(parsed.concepts) == 2
    assert parsed.concepts[0].name == "Embeddings"
    assert parsed.concepts[0].level == "strong"
    assert len(parsed.misconceptions) == 1
    assert len(parsed.gaps) == 2


def test_profile_parser_corrupt_fallback():
    corrupt = "Not a json output at all."
    mock_interactions = [
        {"concept_target": "Vector Indexing", "learner_answer": "I have built production vector search.", "quick_assessment": "Solid"},
        {"concept_target": "Reranking", "learner_answer": "I have never used this.", "quick_assessment": "Unfamiliar"}
    ]
    parsed = parse_knowledge_profile(corrupt, topic="RAG", interactions=mock_interactions)
    assert parsed.overall_confidence in ["beginner", "intermediate", "advanced", "mixed"]
    assert len(parsed.concepts) >= 2
    # First should be strong because learner mentioned 'production'
    assert any(c.level == "strong" for c in parsed.concepts)
    # Second should be weak because learner mentioned 'never'
    assert any(c.level == "weak" for c in parsed.concepts)
    assert len(parsed.gaps) > 0


def test_generate_and_get_profile_flow(client):
    # 1. Create Journey
    j_res = client.post("/journeys", json={"topic": "FastAPI Dependency Injection"})
    assert j_res.status_code == 201
    journey_id = j_res.json()["id"]

    # 2. Trying to get profile before generation yields 404
    get_before = client.get(f"/journeys/{journey_id}/knowledge-profile")
    assert get_before.status_code == 404

    # 3. Trying to generate profile without answering questions yields 400
    gen_before = client.post(f"/journeys/{journey_id}/knowledge-profile")
    assert gen_before.status_code == 400

    # 4. Start discovery & answer 2 questions
    client.post(f"/journeys/{journey_id}/discovery/start")
    ans1 = client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "I use Depends(get_db) frequently in my production APIs to manage sessions."}
    )
    assert ans1.status_code == 200

    ans2 = client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "I have not worked with sub-dependencies or yield cleanups."}
    )
    assert ans2.status_code == 200

    # 5. Generate Knowledge Profile
    gen_res = client.post(f"/journeys/{journey_id}/knowledge-profile")
    assert gen_res.status_code == 200
    p_data = gen_res.json()
    assert p_data["journey_id"] == journey_id
    assert p_data["topic"] == "FastAPI Dependency Injection"
    assert p_data["overall_confidence"] in ["beginner", "intermediate", "advanced", "mixed"]
    assert len(p_data["summary"]) > 10
    assert len(p_data["concepts"]) >= 1
    assert "gaps" in p_data

    # Check journey status updated
    j_check = client.get(f"/journeys/{journey_id}")
    assert j_check.json()["status"] == "profile_ready"

    # 6. Retrieve profile with GET
    get_res = client.get(f"/journeys/{journey_id}/knowledge-profile")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == p_data["id"]
    assert len(get_res.json()["concepts"]) == len(p_data["concepts"])


def test_profile_unknown_journey(client):
    res = client.get("/journeys/non-existent-journey-uuid/knowledge-profile")
    assert res.status_code == 404

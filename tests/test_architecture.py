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

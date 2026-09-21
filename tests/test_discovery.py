import pytest
from backend.app.discovery.parser import (
    parse_initial_question,
    parse_adaptive_step,
    extract_json_object,
)


def test_parser_extract_json_from_markdown():
    text_with_markdown = """Here is the question:
```json
{
  "question": "What is an embedding in the context of vector search?",
  "concept_target": "Embeddings",
  "reasoning": "Baseline probe."
}
```
Hope this helps!"""
    data = extract_json_object(text_with_markdown)
    assert data is not None
    assert data["concept_target"] == "Embeddings"


def test_parser_fallback_on_corrupt_text():
    corrupt_text = "I am an AI and I don't feel like returning JSON."
    parsed_init = parse_initial_question(corrupt_text, topic="RAG")
    assert "RAG" in parsed_init.question or len(parsed_init.question) > 10
    assert parsed_init.concept_target is not None

    parsed_step = parse_adaptive_step(corrupt_text, current_index=1, max_questions=4, topic="RAG")
    assert parsed_step.quick_assessment is not None


def test_parser_enforces_max_questions():
    llm_wants_to_continue = '{"is_finished": false, "next_question": "Another question?", "concept_target": "Test"}'
    parsed = parse_adaptive_step(llm_wants_to_continue, current_index=4, max_questions=4, topic="RAG")
    assert parsed.is_finished is True
    assert parsed.next_question is None


def test_discovery_start(client):
    # 1. Create journey
    j_res = client.post("/journeys", json={"topic": "Retrieval Augmented Generation"})
    assert j_res.status_code == 201
    journey_id = j_res.json()["id"]

    # 2. Start discovery
    start_res = client.post(f"/journeys/{journey_id}/discovery/start")
    assert start_res.status_code == 200
    data = start_res.json()
    assert data["journey_id"] == journey_id
    assert data["question_index"] == 1
    assert len(data["question_text"]) > 5
    assert len(data["concept_target"]) > 0
    assert data["is_finished"] is False

    # Calling start again before answering returns the same pending question
    start_repeat = client.post(f"/journeys/{journey_id}/discovery/start")
    assert start_repeat.status_code == 200
    assert start_repeat.json()["question_index"] == 1
    assert start_repeat.json()["question_text"] == data["question_text"]


def test_discovery_answer_and_history(client):
    # Create journey
    j_res = client.post("/journeys", json={"topic": "Distributed Raft Consensus"})
    journey_id = j_res.json()["id"]

    # Start discovery
    start_res = client.post(f"/journeys/{journey_id}/discovery/start")
    assert start_res.status_code == 200

    # Submit Answer 1
    ans_res = client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "Raft uses leader election and replicated logs to achieve consensus among nodes."},
    )
    assert ans_res.status_code == 200
    ans_data = ans_res.json()
    assert ans_data["question_index"] == 2
    assert ans_data["is_finished"] is False
    assert len(ans_data["question_text"]) > 5

    # Check history
    hist_res = client.get(f"/journeys/{journey_id}/discovery")
    assert hist_res.status_code == 200
    hist_data = hist_res.json()
    assert len(hist_data["interactions"]) >= 2
    q1 = hist_data["interactions"][0]
    assert q1["question_index"] == 1
    assert "leader election" in q1["learner_answer"]


def test_discovery_full_cycle_completion(client):
    j_res = client.post("/journeys", json={"topic": "eBPF Linux Kernel"})
    journey_id = j_res.json()["id"]

    client.post(f"/journeys/{journey_id}/discovery/start")

    # Answer up to 4 times or until is_finished
    finished = False
    for i in range(1, 5):
        ans_res = client.post(
            f"/journeys/{journey_id}/discovery/answer",
            json={"answer": f"Answer for turn {i}: I have basic conceptual knowledge about this subtopic."},
        )
        assert ans_res.status_code == 200
        if ans_res.json()["is_finished"]:
            finished = True
            break

    assert finished is True

    # Check journey status updated
    get_j = client.get(f"/journeys/{journey_id}")
    assert get_j.status_code == 200
    assert get_j.json()["status"] == "discovery_completed"


def test_discovery_empty_answer_rejected(client):
    j_res = client.post("/journeys", json={"topic": "Vector Databases"})
    journey_id = j_res.json()["id"]
    client.post(f"/journeys/{journey_id}/discovery/start")

    bad_ans = client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "   "},
    )
    assert bad_ans.status_code == 422


def test_discovery_unknown_journey(client):
    res = client.post("/journeys/unknown-id-123/discovery/start")
    assert res.status_code == 404

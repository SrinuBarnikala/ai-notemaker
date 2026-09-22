import pytest


def helper_setup_note_for_assessment(client, topic: str = "Distributed Consensus Algorithms"):
    # 1. Create Journey
    res = client.post("/journeys", json={"topic": topic})
    assert res.status_code == 201
    journey_id = res.json()["id"]

    # 2. Advance through discovery, profile, architecture, note
    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "I know basic leader election but struggle with log compaction."},
    )
    client.post(f"/journeys/{journey_id}/knowledge-profile")
    client.post(f"/journeys/{journey_id}/architecture")
    note_res = client.post(f"/journeys/{journey_id}/generate-note")
    assert note_res.status_code == 200
    return journey_id, note_res.json()


def test_generate_and_get_assessment_flow(client):
    journey_id, note = helper_setup_note_for_assessment(client, "Raft Protocol Internals")

    # 1. Generate assessment
    res = client.post(f"/journeys/{journey_id}/assessment/generate")
    assert res.status_code == 200
    data = res.json()

    assert data["journey_id"] == journey_id
    assert data["note_id"] == note["id"]
    assert len(data["flashcards"]) >= 3
    assert len(data["quiz_questions"]) >= 3

    # Check flashcard schema
    fc = data["flashcards"][0]
    assert "id" in fc
    assert "concept" in fc
    assert "front" in fc
    assert "back" in fc
    assert fc["difficulty"] in ["easy", "medium", "hard"]

    # Check quiz question schema
    qq = data["quiz_questions"][0]
    assert "id" in qq
    assert "question" in qq
    assert len(qq["options"]) >= 2
    assert 0 <= qq["correct_index"] < len(qq["options"])
    assert "explanation" in qq

    # 2. Retrieve assessment
    get_res = client.get(f"/journeys/{journey_id}/assessment")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["id"] == data["id"]
    assert len(get_data["flashcards"]) == len(data["flashcards"])
    assert len(get_data["quiz_questions"]) == len(data["quiz_questions"])


def test_quiz_submission_and_profile_progression(client):
    journey_id, note = helper_setup_note_for_assessment(client, "Kubernetes Custom Resource Controllers")

    # Generate assessment
    gen_res = client.post(f"/journeys/{journey_id}/assessment/generate")
    assert gen_res.status_code == 200
    quiz_questions = gen_res.json()["quiz_questions"]

    # Submit all correct answers
    answers = {q["id"]: q["correct_index"] for q in quiz_questions}
    sub_res = client.post(
        f"/journeys/{journey_id}/assessment/submit",
        json={"answers": answers},
    )
    assert sub_res.status_code == 200
    result = sub_res.json()

    assert result["score"] == len(quiz_questions)
    assert result["percentage"] == 100.0
    assert result["updated_confidence"] == "advanced"
    assert len(result["breakdown"]) == len(quiz_questions)
    for item in result["breakdown"]:
        assert item["is_correct"] is True

    # Check that knowledge profile reflects advanced confidence
    prof_res = client.get(f"/journeys/{journey_id}/knowledge-profile")
    assert prof_res.status_code == 200
    prof_data = prof_res.json()
    assert prof_data["overall_confidence"] == "advanced"


def test_assessment_errors(client):
    # Unknown journey
    res = client.post("/journeys/unknown-uuid-0000/assessment/generate")
    assert res.status_code == 404

    # Journey without note cannot generate assessment
    j_res = client.post("/journeys", json={"topic": "WebRTC Peer Connections"})
    jid = j_res.json()["id"]
    bad_res = client.post(f"/journeys/{jid}/assessment/generate")
    assert bad_res.status_code == 400

    # Assessment not yet generated
    get_res = client.get(f"/journeys/{jid}/assessment")
    assert get_res.status_code == 404

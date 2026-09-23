import pytest
from fastapi.testclient import TestClient


def create_sample_journey_and_note(client: TestClient) -> dict:
    """Helper to spin up a full journey with note for copilot tests."""
    j_res = client.post("/journeys", json={"topic": "Distributed Consensus & Raft"})
    assert j_res.status_code == 201
    journey = j_res.json()
    journey_id = journey["id"]

    # Start discovery
    d_start = client.post(f"/journeys/{journey_id}/discovery/start")
    assert d_start.status_code == 200

    # Answer probe
    d_ans = client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "I know leader elections and log replication, but split-brain recovery is a gap."},
    )
    assert d_ans.status_code == 200

    # Generate profile
    p_res = client.post(f"/journeys/{journey_id}/knowledge-profile")
    assert p_res.status_code == 200

    # Generate architecture
    a_res = client.post(f"/journeys/{journey_id}/architecture")
    assert a_res.status_code == 200

    # Generate living note
    n_res = client.post(f"/journeys/{journey_id}/generate-note")
    assert n_res.status_code == 200
    note = n_res.json()

    return {
        "journey_id": journey_id,
        "note": note,
    }


def test_copilot_ask_grounded_flow(client: TestClient):
    data = create_sample_journey_and_note(client)
    journey_id = data["journey_id"]
    note = data["note"]
    section_id = note["sections"][0]["id"]

    res = client.post(
        f"/journeys/{journey_id}/copilot/ask",
        json={
            "question": "Why does Raft use randomized election timeouts instead of fixed?",
            "section_id": section_id,
            "history": [
                {"role": "user", "content": "How do candidates start election?"},
                {"role": "assistant", "content": "They increment current term and transition to candidate state."},
            ],
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["journey_id"] == journey_id
    assert payload["section_id"] == section_id
    assert len(payload["answer"]) > 10
    assert len(payload["suggested_followups"]) > 0
    assert payload["pin_candidate"] is not None
    assert payload["pin_candidate"]["content"]


def test_copilot_ask_with_selected_text(client: TestClient):
    data = create_sample_journey_and_note(client)
    journey_id = data["journey_id"]
    note = data["note"]
    section_id = note["sections"][0]["id"]

    res = client.post(
        f"/journeys/{journey_id}/copilot/ask",
        json={
            "question": "Can you explain this excerpt in simpler terms?",
            "section_id": section_id,
            "selected_text": "Heartbeats prevent election timeouts by resetting candidate countdowns.",
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["journey_id"] == journey_id
    assert "answer" in payload
    assert len(payload["suggested_followups"]) > 0


def test_copilot_pin_answer_to_note(client: TestClient):
    data = create_sample_journey_and_note(client)
    journey_id = data["journey_id"]
    note = data["note"]
    note_id = note["id"]
    initial_version = note["version"]
    section_id = note["sections"][0]["id"]
    initial_block_count = len(note["sections"][0]["blocks"])

    pin_res = client.post(
        f"/journeys/{journey_id}/copilot/pin",
        json={
            "section_id": section_id,
            "block_type": "warning",
            "title": "Split-Brain Invariant",
            "content": "A quorum must strictly exceed N/2 to prevent simultaneous conflicting leaders.",
        },
    )
    assert pin_res.status_code == 200
    pin_data = pin_res.json()
    assert pin_data["success"] is True
    assert pin_data["note_version"] == initial_version + 1

    # Verify note updated via GET
    get_res = client.get(f"/notes/{note_id}")
    assert get_res.status_code == 200
    updated_note = get_res.json()
    assert updated_note["version"] == initial_version + 1

    # Find the target section
    sec = next(s for s in updated_note["sections"] if s["id"] == section_id)
    assert len(sec["blocks"]) == initial_block_count + 1
    new_block = sec["blocks"][-1]
    assert new_block["type"] == "warning"
    assert new_block["title"] == "Split-Brain Invariant"
    assert "quorum" in new_block["content"]

    # Verify revision was recorded
    assert len(updated_note["revisions"]) > 0
    latest_rev = updated_note["revisions"][-1]
    assert latest_rev["evolution_type"] == "copilot_pin"
    assert latest_rev["version"] == initial_version + 1


def test_copilot_error_handling(client: TestClient):
    # Nonexistent journey
    res = client.post(
        "/journeys/nonexistent-id/copilot/ask",
        json={"question": "What is this?"},
    )
    assert res.status_code == 404

    # Nonexistent section on pin
    data = create_sample_journey_and_note(client)
    journey_id = data["journey_id"]
    pin_res = client.post(
        f"/journeys/{journey_id}/copilot/pin",
        json={
            "section_id": "nonexistent-sec-id",
            "block_type": "paragraph",
            "content": "Some text",
        },
    )
    assert pin_res.status_code == 404


def test_copilot_frontend_elements_present(client: TestClient):
    """Verify index.html includes Copilot drawer, floating ask badge, and copilot.js."""
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    assert "copilot-drawer" in html
    assert "floating-ask-badge" in html
    assert "btn-copilot-toggle" in html
    assert "copilot.js" in html

import pytest
from starlette.testclient import TestClient
from backend.app.main import app




def helper_setup_note(client, topic: str = "Distributed Tracing with OpenTelemetry"):
    # 1. Create Journey
    res = client.post("/journeys", json={"topic": topic})
    assert res.status_code == 201
    journey_id = res.json()["id"]

    # 2. Advance through discovery, profile, architecture, note
    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "I know basic logging, but need distributed context propagation."},
    )
    client.post(f"/journeys/{journey_id}/knowledge-profile")
    client.post(f"/journeys/{journey_id}/architecture")
    note_res = client.post(f"/journeys/{journey_id}/generate-note")
    assert note_res.status_code == 200
    return journey_id, note_res.json()


def test_evolve_section_adds_code_and_bumps_version(client):
    journey_id, note = helper_setup_note(client, "Distributed Tracing Architecture")
    note_id = note["id"]
    assert note["version"] == 1
    assert len(note["revisions"]) == 0

    first_sec = note["sections"][0]
    sec_id = first_sec["id"]

    # Evolve Section with add_code
    evolve_res = client.post(
        f"/journeys/{journey_id}/note/evolve",
        json={
            "evolution_type": "add_code",
            "section_id": sec_id,
            "user_prompt": "Please add a production OpenTelemetry Python tracer setup.",
        },
    )
    assert evolve_res.status_code == 200
    updated_data = evolve_res.json()

    assert updated_data["version"] == 2
    assert len(updated_data["revisions"]) == 1
    rev = updated_data["revisions"][0]
    assert rev["version"] == 2
    assert rev["evolution_type"] == "add_code"
    assert rev["section_title"] == first_sec["title"]
    assert "OpenTelemetry" in rev["user_prompt"]

    # Verify section was updated
    updated_first_sec = next(s for s in updated_data["sections"] if s["id"] == sec_id)
    assert len(updated_first_sec["blocks"]) > 0


def test_evolve_by_note_id_direct(client):
    journey_id, note = helper_setup_note(client, "Raft Leader Election")
    note_id = note["id"]
    sec_id = note["sections"][0]["id"]

    evolve_res = client.post(
        f"/notes/{note_id}/evolve",
        json={
            "evolution_type": "expand_section",
            "section_id": sec_id,
            "user_prompt": "Provide deeper technical breakdown of heartbeat timers.",
        },
    )
    assert evolve_res.status_code == 200
    data = evolve_res.json()
    assert data["version"] == 2
    assert len(data["revisions"]) == 1
    assert data["revisions"][0]["evolution_type"] == "expand_section"


def test_evolve_add_section(client):
    journey_id, note = helper_setup_note(client, "Database Sharding Patterns")
    initial_sec_count = len(note["sections"])

    evolve_res = client.post(
        f"/journeys/{journey_id}/note/evolve",
        json={
            "evolution_type": "add_section",
            "user_prompt": "Consistent Hashing Ring Implementation",
        },
    )
    assert evolve_res.status_code == 200
    data = evolve_res.json()
    assert data["version"] == 2
    assert len(data["sections"]) == initial_sec_count + 1
    new_sec = data["sections"][-1]
    assert "Consistent Hashing" in new_sec["title"]


def test_evolve_invalid_journey_or_section(client):
    # Unknown journey
    res = client.post(
        "/journeys/invalid-uuid-9999/note/evolve",
        json={"evolution_type": "custom_prompt", "user_prompt": "test"},
    )
    assert res.status_code == 404

    # Unknown note id
    res2 = client.post(
        "/notes/invalid-note-uuid-9999/evolve",
        json={"evolution_type": "custom_prompt", "user_prompt": "test"},
    )
    assert res2.status_code == 404

    # Valid note, invalid section ID
    journey_id, note = helper_setup_note(client, "Kafka Partition Rebalancing")
    res3 = client.post(
        f"/notes/{note['id']}/evolve",
        json={
            "evolution_type": "expand_section",
            "section_id": "nonexistent-section-id-123",
            "user_prompt": "test",
        },
    )
    assert res3.status_code == 404


def test_export_note_markdown(client):
    journey_id, note = helper_setup_note(client, "Zero-Knowledge Proofs Architecture")
    note_id = note["id"]

    # Export via note_id
    res = client.get(f"/notes/{note_id}/export?format=markdown")
    assert res.status_code == 200
    assert "text/markdown" in res.headers["content-type"]
    assert "attachment; filename=" in res.headers["content-disposition"]
    md_content = res.text

    assert "---" in md_content
    assert "title: \"Zero-Knowledge Proofs Architecture\"" in md_content
    assert "version: 1" in md_content
    assert "# Zero-Knowledge Proofs Architecture" in md_content
    assert "## Table of Contents" in md_content

    # Export via journey_id
    j_res = client.get(f"/journeys/{journey_id}/note/export?format=markdown")
    assert j_res.status_code == 200
    assert j_res.text == md_content


def test_export_note_json(client):
    journey_id, note = helper_setup_note(client, "GraphQL Subscriptions with WebSockets")
    note_id = note["id"]

    res = client.get(f"/notes/{note_id}/export?format=json")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == note_id
    assert data["topic"] == "GraphQL Subscriptions with WebSockets"
    assert "sections" in data
    assert "revisions" in data

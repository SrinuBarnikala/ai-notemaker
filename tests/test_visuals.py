import pytest
from starlette.testclient import TestClient
from backend.app.main import app
from backend.app.visuals.sanitizer import (
    sanitize_mermaid_spec,
    generate_fallback_mermaid,
    extract_json,
)


def helper_setup_note(client, topic: str = "Distributed Consensus with Raft"):
    res = client.post("/journeys", json={"topic": topic})
    assert res.status_code == 201
    journey_id = res.json()["id"]

    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "I understand leader election, but struggle with log replication and split votes."},
    )
    client.post(f"/journeys/{journey_id}/knowledge-profile")
    client.post(f"/journeys/{journey_id}/architecture")
    note_res = client.post(f"/journeys/{journey_id}/generate-note")
    assert note_res.status_code == 200
    return journey_id, note_res.json()


def test_mermaid_sanitizer_and_fallbacks():
    # 1. Strips markdown fences
    raw = "```mermaid\nflowchart TD\n    A --> B\n```"
    cleaned = sanitize_mermaid_spec(raw)
    assert "```" not in cleaned
    assert "flowchart TD" in cleaned

    # 2. Auto-quotes labels with parentheses
    raw_unquoted = "flowchart LR\n    Client[Web Client (HTTP)] --> GW[API Gateway (Envoy)]"
    cleaned_quotes = sanitize_mermaid_spec(raw_unquoted)
    assert 'Client["Web Client (HTTP)"]' in cleaned_quotes
    assert 'GW["API Gateway (Envoy)"]' in cleaned_quotes

    # 3. Auto-prefixes arrows if keyword missing
    arrow_spec = "A --> B --> C"
    cleaned_arrow = sanitize_mermaid_spec(arrow_spec)
    assert cleaned_arrow.startswith("flowchart TD")

    # 4. Fallbacks for all visual paradigms
    for v_type in ["flowchart", "sequence", "architecture", "state_machine", "concept_map"]:
        fb = generate_fallback_mermaid(v_type, "Distributed Consensus")
        assert len(fb) > 20
        assert "Distributed Consensus" in fb


def test_plan_visuals_full_flow(client):
    journey_id, note = helper_setup_note(client, "High-Throughput Kafka Partitioning")
    note_id = note["id"]

    # Plan visuals for note
    res = client.post(f"/journeys/{journey_id}/visuals/plan")
    assert res.status_code == 200
    data = res.json()

    assert data["journey_id"] == journey_id
    assert data["note_id"] == note_id
    assert data["total_diagrams"] >= 1
    assert len(data["visuals"]) >= 1

    first_visual = data["visuals"][0]
    assert "diagram_spec" in first_visual
    assert len(first_visual["diagram_spec"]) > 10
    assert first_visual["needs_visual"] is True

    # Retrieve visuals endpoint
    get_res = client.get(f"/journeys/{journey_id}/visuals")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["total_diagrams"] == data["total_diagrams"]

    # Verify Note retrieval reflects diagram blocks
    note_fetch = client.get(f"/journeys/{journey_id}/note")
    assert note_fetch.status_code == 200
    fetched_note = note_fetch.json()
    all_blocks = [b for sec in fetched_note["sections"] for b in sec["blocks"]]
    diagram_blocks = [b for b in all_blocks if b["type"] == "diagram"]
    assert len(diagram_blocks) >= 1
    assert diagram_blocks[0]["diagram_spec"] is not None


def test_generate_section_visual(client):
    journey_id, note = helper_setup_note(client, "Raft Log Compaction Architecture")
    first_sec = note["sections"][0]
    sec_id = first_sec["id"]

    # Generate sequence diagram for this section
    res = client.post(
        f"/journeys/{journey_id}/sections/{sec_id}/visual",
        json={
            "visual_type": "sequence",
            "custom_prompt": "Show leader log replication handshake with follower heartbeat timeout.",
            "title": "Raft Leader Heartbeat & Replication Sequence",
        },
    )
    assert res.status_code == 200
    data = res.json()

    assert data["journey_id"] == journey_id
    assert data["section_id"] == sec_id
    assert data["diagram_block"]["type"] == "diagram"
    assert data["diagram_block"]["diagram_type"] == "sequence"
    assert "sequenceDiagram" in data["diagram_block"]["diagram_spec"]
    assert "Raft" in data["diagram_block"]["title"]


def test_visuals_error_handling(client):
    # Unknown journey
    res = client.post("/journeys/unknown-id/visuals/plan")
    assert res.status_code == 404

    # Journey without note
    new_j = client.post("/journeys", json={"topic": "Vector Databases"}).json()
    res_no_note = client.post(f"/journeys/{new_j['id']}/visuals/plan")
    assert res_no_note.status_code == 404
    assert "Phase 5" in res_no_note.json()["detail"]

    # Unknown section for valid journey
    journey_id, _ = helper_setup_note(client, "Database Isolation Levels")
    res_bad_sec = client.post(
        f"/journeys/{journey_id}/sections/bad-section-id/visual",
        json={"visual_type": "flowchart"},
    )
    assert res_bad_sec.status_code == 404

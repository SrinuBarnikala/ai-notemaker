import pytest
from fastapi.testclient import TestClient


def create_sample_journey_for_versioning(client: TestClient) -> dict:
    """Helper to spin up a journey with profile, architecture, and living note."""
    j_res = client.post("/journeys", json={"topic": "Distributed Consensus & Raft Protocol"})
    assert j_res.status_code == 201
    journey = j_res.json()
    journey_id = journey["id"]

    # Start discovery
    d_start = client.post(f"/journeys/{journey_id}/discovery/start")
    assert d_start.status_code == 200

    # Answer probe
    d_ans = client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "I understand state machines, but leader election and log replication are gaps."},
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


def test_initial_generation_creates_version_1_snapshot(client: TestClient):
    data = create_sample_journey_for_versioning(client)
    journey_id = data["journey_id"]
    note = data["note"]
    note_id = note["id"]

    assert note["version"] == 1
    assert len(note["sections"]) >= 1

    # Check /notes/{note_id}/versions
    res = client.get(f"/notes/{note_id}/versions")
    assert res.status_code == 200
    payload = res.json()

    assert payload["note_id"] == note_id
    assert payload["current_version"] == 1
    assert payload["total_versions"] == 1
    assert len(payload["versions"]) == 1

    v1 = payload["versions"][0]
    assert v1["version"] == 1
    assert v1["is_current"] is True
    assert v1["total_sections"] == len(note["sections"])
    assert "Initial living note" in v1["change_summary"]

    # Check journey versions route
    j_res = client.get(f"/journeys/{journey_id}/note/versions")
    assert j_res.status_code == 200
    assert j_res.json()["current_version"] == 1


def test_evolution_creates_version_2_snapshot_and_diff(client: TestClient):
    data = create_sample_journey_for_versioning(client)
    journey_id = data["journey_id"]
    note = data["note"]
    note_id = note["id"]
    first_section = note["sections"][0]

    # Evolve section (add code) -> Bumps to Version 2
    evolve_res = client.post(
        f"/notes/{note_id}/evolve",
        json={
            "evolution_type": "add_code",
            "section_id": first_section["id"],
            "user_prompt": "Provide production-ready Python code demonstrating Raft leader election timer",
        },
    )
    assert evolve_res.status_code == 200
    v2_note = evolve_res.json()
    assert v2_note["version"] == 2

    # Check versions list has v1 and v2
    v_res = client.get(f"/notes/{note_id}/versions")
    assert v_res.status_code == 200
    v_payload = v_res.json()
    assert v_payload["current_version"] == 2
    assert v_payload["total_versions"] == 2

    # Verify v1 snapshot retrieval
    v1_res = client.get(f"/notes/{note_id}/versions/1")
    assert v1_res.status_code == 200
    v1_data = v1_res.json()
    assert v1_data["version"] == 1

    # Verify v2 snapshot retrieval
    v2_res = client.get(f"/notes/{note_id}/versions/2")
    assert v2_res.status_code == 200
    v2_data = v2_res.json()
    assert v2_data["version"] == 2

    # Compute diff between Version 1 and Version 2
    diff_res = client.get(f"/notes/{note_id}/diff?from_version=1&to_version=2")
    assert diff_res.status_code == 200
    diff = diff_res.json()

    assert diff["from_version"] == 1
    assert diff["to_version"] == 2
    assert diff["stats"]["sections_modified"] >= 1
    assert diff["stats"]["blocks_added"] >= 1 or diff["stats"]["blocks_modified"] >= 1
    assert "Changes from Version 1 to 2" in diff["summary"]

    # Journey diff endpoint
    j_diff_res = client.get(f"/journeys/{journey_id}/note/diff?from_version=1&to_version=2")
    assert j_diff_res.status_code == 200
    assert j_diff_res.json()["from_version"] == 1


def test_restore_version_flow(client: TestClient):
    data = create_sample_journey_for_versioning(client)
    journey_id = data["journey_id"]
    note = data["note"]
    note_id = note["id"]
    v1_section_count = len(note["sections"])

    # Add a new section -> creates Version 2
    evolve_res = client.post(
        f"/notes/{note_id}/evolve",
        json={
            "evolution_type": "add_section",
            "user_prompt": "Byzantine Fault Tolerance and Edge Cases in Raft",
        },
    )
    assert evolve_res.status_code == 200
    assert evolve_res.json()["version"] == 2
    assert len(evolve_res.json()["sections"]) == v1_section_count + 1

    # Restore to Version 1 -> creates Version 3 (non-destructive rollback)
    restore_res = client.post(f"/notes/{note_id}/versions/1/restore")
    assert restore_res.status_code == 200
    restore_payload = restore_res.json()

    assert restore_payload["success"] is True
    assert restore_payload["restored_from_version"] == 1
    assert restore_payload["new_version"] == 3
    assert len(restore_payload["note"]["sections"]) == v1_section_count

    # Check versions list now contains v1, v2, v3
    v_res = client.get(f"/notes/{note_id}/versions")
    assert v_res.status_code == 200
    assert v_res.json()["current_version"] == 3
    assert v_res.json()["total_versions"] == 3

    # Check journey restore endpoint
    j_restore_res = client.post(f"/journeys/{journey_id}/note/versions/2/restore")
    assert j_restore_res.status_code == 200
    assert j_restore_res.json()["new_version"] == 4


def test_versioning_error_handling(client: TestClient):
    # Non-existent note
    res = client.get("/notes/fake-note-9999/versions")
    assert res.status_code == 404

    res = client.get("/notes/fake-note-9999/versions/1")
    assert res.status_code == 404

    res = client.get("/notes/fake-note-9999/diff?from_version=1&to_version=2")
    assert res.status_code == 404

    res = client.post("/notes/fake-note-9999/versions/1/restore")
    assert res.status_code == 404

    # Non-existent journey
    res = client.get("/journeys/fake-journey-9999/note/versions")
    assert res.status_code == 404


def test_versioning_frontend_elements_present(client: TestClient):
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    # We will ensure these elements are in frontend/index.html
    assert "version-history-modal" in html
    assert "btn-view-versions" in html
    assert "version-diff-container" in html

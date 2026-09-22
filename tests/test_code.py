import pytest
from starlette.testclient import TestClient
from backend.app.code.sanitizer import (
    sanitize_code_block,
    generate_fallback_code,
    extract_json,
)


def helper_setup_note(client, topic: str = "Consistent Hashing Ring Architecture"):
    res = client.post("/journeys", json={"topic": topic})
    assert res.status_code == 201
    journey_id = res.json()["id"]

    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "I know basic hash tables, but want to master virtual nodes and ring wrap-around."},
    )
    client.post(f"/journeys/{journey_id}/knowledge-profile")
    client.post(f"/journeys/{journey_id}/architecture")
    note_res = client.post(f"/journeys/{journey_id}/generate-note")
    assert note_res.status_code == 200
    return journey_id, note_res.json()


def test_code_sanitizer_and_fallbacks():
    # 1. Strips markdown fences
    raw = "```python\ndef compute_hash(key: str) -> int:\n    return hash(key)\n```"
    cleaned = sanitize_code_block(raw, "python")
    assert "```" not in cleaned
    assert "compute_hash" in cleaned

    # 2. Generates deterministic fallbacks for different languages
    py_fb = generate_fallback_code("Consistent Hashing", "Virtual Node Ring", "python")
    assert py_fb["language"] == "python"
    assert py_fb["runnable"] is True
    assert "__main__" in py_fb["code"]
    assert "Time:" in py_fb["complexity"]
    assert py_fb["expected_output"] is not None

    sql_fb = generate_fallback_code("Database Partitioning", "Telemetry Analysis", "sql")
    assert sql_fb["language"] == "sql"
    assert sql_fb["runnable"] is False
    assert "SELECT" in sql_fb["code"]

    bash_fb = generate_fallback_code("Kubernetes Pod Scheduling", "Deployment Script", "bash")
    assert bash_fb["language"] == "bash"
    assert bash_fb["runnable"] is False
    assert "set -euo pipefail" in bash_fb["code"]


def test_plan_code_full_flow(client):
    journey_id, note = helper_setup_note(client, "Distributed Consensus with Raft")
    note_id = note["id"]

    # Plan code for note
    res = client.post(f"/journeys/{journey_id}/code/plan")
    assert res.status_code == 200
    data = res.json()
    assert data["journey_id"] == journey_id
    assert data["note_id"] == note_id
    assert len(data["code_items"]) > 0
    assert data["total_code_blocks"] == len(data["code_items"])

    # Verify first code item
    first_item = data["code_items"][0]
    assert first_item["language"] in ["python", "go", "rust", "typescript", "sql", "bash"]
    assert len(first_item["code"]) > 20
    assert first_item["complexity"] is not None

    # Verify that the note in DB now has code blocks with runnable & complexity
    note_res = client.get(f"/journeys/{journey_id}/note")
    assert note_res.status_code == 200
    updated_sections = note_res.json()["sections"]

    has_code_block = False
    for sec in updated_sections:
        for block in sec["blocks"]:
            if block["type"] == "code":
                has_code_block = True
                assert block["code"] is not None
                assert block["language"] is not None
                break
        if has_code_block:
            break

    assert has_code_block is True


def test_generate_section_code(client):
    journey_id, note = helper_setup_note(client, "LSM-Trees and SSTables")
    first_section = note["sections"][0]
    section_id = first_section["id"]

    # Generate Python code for section
    res = client.post(
        f"/journeys/{journey_id}/sections/{section_id}/code",
        json={
            "language": "python",
            "purpose": "Implement MemTable skip-list flush mechanism",
            "include_tests": True,
            "custom_prompt": "Write a working MemTable in-memory buffer with key-value write and flush to list.",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["journey_id"] == journey_id
    assert data["section_id"] == section_id
    assert data["code_block"]["type"] == "code"
    assert data["code_block"]["language"] == "python"
    assert data["code_block"]["runnable"] is True
    assert len(data["code_block"]["code"]) > 20
    assert data["code_block"]["complexity"] is not None

    # Retrieve all code blocks via GET
    get_res = client.get(f"/journeys/{journey_id}/code")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["journey_id"] == journey_id
    assert get_data["total_code_blocks"] >= 1


def test_code_error_handling(client):
    # Unknown journey
    res = client.post("/journeys/non-existent-uuid/code/plan")
    assert res.status_code == 404

    # Unknown section
    journey_id, note = helper_setup_note(client, "Vector Search Indexing")
    sec_res = client.post(
        f"/journeys/{journey_id}/sections/non-existent-section-id/code",
        json={"language": "python"},
    )
    assert sec_res.status_code == 404

    # Get code for unknown journey
    get_res = client.get("/journeys/non-existent-uuid/code")
    assert get_res.status_code == 404

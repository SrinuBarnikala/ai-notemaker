import pytest
from backend.app.note.parser import parse_section_blocks


def test_parse_section_blocks_valid_json():
    raw_json = """
    [
      {
        "type": "paragraph",
        "content": "Reranking evaluates documents jointly with the query."
      },
      {
        "type": "definition",
        "term": "Cross-Encoder",
        "content": "A model that scores query-document pairs simultaneously."
      },
      {
        "type": "code",
        "language": "python",
        "title": "Cross-Encoder Scoring",
        "code": "model.predict([('query', 'doc1'), ('query', 'doc2')])"
      },
      {
        "type": "warning",
        "title": "Computational Overhead",
        "content": "Cross-encoders cannot precompute document embeddings."
      }
    ]
    """
    blocks = parse_section_blocks(
        raw_text=raw_json,
        section_title="Reranking Mechanics",
        section_type="deep_dive",
        depth="deep",
        target_concepts=["Reranking"],
        rationale="Deep dive into cross-encoders.",
        needs_code=True,
        needs_visual=False,
    )
    assert len(blocks) == 4
    assert blocks[0].type == "paragraph"
    assert blocks[1].type == "definition"
    assert blocks[1].term == "Cross-Encoder"
    assert blocks[2].type == "code"
    assert blocks[2].language == "python"
    assert blocks[3].type == "warning"


def test_parse_section_blocks_fallback():
    corrupt = "Not a json array."
    blocks = parse_section_blocks(
        raw_text=corrupt,
        section_title="Mental Model Realignment",
        section_type="pitfall_warning",
        depth="standard",
        target_concepts=["Reranking vs Retrieval"],
        rationale="Corrects misconception.",
        needs_code=True,
        needs_visual=True,
        visual_type="architecture_diagram",
    )
    assert len(blocks) >= 4
    block_types = [b.type for b in blocks]
    assert "paragraph" in block_types
    assert "warning" in block_types
    assert "diagram" in block_types
    assert "code" in block_types


def test_generate_and_get_note_flow(client):
    # 1. Create Journey
    j_res = client.post("/journeys", json={"topic": "Vector Databases"})
    assert j_res.status_code == 201
    journey_id = j_res.json()["id"]

    # 2. Cannot generate note without architecture -> 400
    bad_gen = client.post(f"/journeys/{journey_id}/generate-note")
    assert bad_gen.status_code == 400

    # 3. Complete Discovery, Profile, Architecture
    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "I know relational DBs well, but vector index math is new."},
    )
    client.post(f"/journeys/{journey_id}/knowledge-profile")
    client.post(f"/journeys/{journey_id}/architecture")

    # 4. Generate Note
    note_res = client.post(f"/journeys/{journey_id}/generate-note")
    assert note_res.status_code == 200
    data = note_res.json()
    assert data["journey_id"] == journey_id
    assert data["topic"] == "Vector Databases"
    assert data["version"] == 1
    assert len(data["sections"]) >= 3
    note_id = data["id"]

    # Check journey status updated
    j_check = client.get(f"/journeys/{journey_id}")
    assert j_check.json()["status"] == "note_generated"

    # Check block structure
    first_section = data["sections"][0]
    assert len(first_section["blocks"]) >= 1

    # 5. Retrieve note by journey ID
    get_by_j = client.get(f"/journeys/{journey_id}/note")
    assert get_by_j.status_code == 200
    assert get_by_j.json()["id"] == note_id

    # 6. Retrieve note by note ID
    get_by_id = client.get(f"/notes/{note_id}")
    assert get_by_id.status_code == 200
    assert get_by_id.json()["topic"] == "Vector Databases"


def test_note_not_found(client):
    res = client.get("/journeys/unknown-id-54321/note")
    assert res.status_code == 404

    res2 = client.get("/notes/unknown-note-id-12345")
    assert res2.status_code == 404

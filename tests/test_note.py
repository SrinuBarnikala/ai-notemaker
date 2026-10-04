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


def test_parse_section_blocks_markdown_table_conversion():
    raw_json = """
    [
      {
        "type": "comparison",
        "title": "Protocol Latency & Consistency Trade-offs",
        "content": "| Protocol | Latency | Guarantees |\\n|---|---|---|\\n| Paxos | 2 RTTs | Linearizable |\\n| Raft | 2 RTTs | Linearizable |\\n| 2PC | 3 RTTs | Atomic Commit |"
      }
    ]
    """
    blocks = parse_section_blocks(
        raw_text=raw_json,
        section_title="Consensus Mechanics",
        section_type="deep_dive",
        depth="standard",
        target_concepts=["Consensus"],
        rationale="Comparison of consensus mechanisms.",
        needs_code=False,
        needs_visual=False,
    )
    assert len(blocks) == 1
    assert blocks[0].type == "comparison"
    assert blocks[0].items is not None
    assert len(blocks[0].items) == 3
    assert blocks[0].items[0]["Protocol"] == "Paxos"
    assert blocks[0].items[0]["Latency"] == "2 RTTs"
    assert blocks[0].items[2]["Guarantees"] == "Atomic Commit"


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


def test_sanitize_latex_text():
    from backend.app.note.parser import sanitize_latex_text

    raw = f"Loss gradient: ${chr(12)}rac{{partial L}}{{partial z}} = {chr(12)}rac{{partial L}}{{partial a}},sigma'(z)$"
    cleaned = sanitize_latex_text(raw)
    assert cleaned == "Loss gradient: $\\frac{\\partial L}{\\partial z} = \\frac{\\partial L}{\\partial a},\\sigma'(z)$"

    step = f"$w leftarrow w - eta,{chr(12)}rac{{partial L}}{{partial w}}$"
    cleaned_step = sanitize_latex_text(step)
    assert cleaned_step == "$w \\leftarrow w - \\eta,\\frac{\\partial L}{\\partial w}$"


def test_parse_section_blocks_with_cpp_fallback():
    corrupt = "Not a json array."
    blocks = parse_section_blocks(
        raw_text=corrupt,
        section_title="Stack Operations",
        section_type="code_walkthrough",
        depth="standard",
        target_concepts=["Stack Mechanics"],
        rationale="Implements stack operations.",
        needs_code=True,
        needs_visual=False,
        preferred_language="cpp",
    )
    code_blocks = [b for b in blocks if b.type == "code"]
    assert len(code_blocks) == 1
    assert code_blocks[0].language == "cpp"
    assert "class" in code_blocks[0].code
    assert "#include <iostream>" in code_blocks[0].code


def test_parse_section_blocks_preserves_llm_cpp_language():
    raw_json = """
    {
      "blocks": [
        {
          "type": "code",
          "language": "cpp",
          "title": "Stack in C++",
          "code": "#include <stack>\\nstd::stack<int> s;"
        }
      ]
    }
    """
    blocks = parse_section_blocks(
        raw_text=raw_json,
        section_title="Stack Implementation",
        section_type="code_walkthrough",
        depth="standard",
        target_concepts=["Stack"],
        rationale="C++ stack implementation.",
        needs_code=True,
        needs_visual=False,
        preferred_language="cpp",
    )
    assert len(blocks) == 1
    assert blocks[0].type == "code"
    assert blocks[0].language == "cpp"
    assert "#include <stack>" in blocks[0].code


@pytest.mark.asyncio
async def test_note_generation_prompt_receives_user_preferred_language():
    import json
    import uuid
    from unittest.mock import patch
    from backend.app.note.generator import generate_structured_note
    from backend.app.models.user import User
    from backend.app.models.user_profile import UserProfile
    from backend.app.models.journey import LearningJourney
    from backend.app.models.profile import KnowledgeProfile
    from backend.app.models.architecture import NoteArchitecture, NoteArchitectureSection
    from backend.app.db.session import SessionLocal
    from backend.app.config import get_settings
    from backend.app.providers.mock import MockLLMProvider

    db = SessionLocal()
    try:
        user = User(
            email=f"srinu_test_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="pw",
        )
        db.add(user)
        db.commit()

        up = UserProfile(
            user_id=user.id,
            experience_level="intermediate",
            preferred_language="cpp",
            explanation_depth="internals",
            learning_style="code_and_visual",
        )
        db.add(up)

        journey = LearningJourney(
            user_id=user.id,
            topic="Stack in DSA",
            status="architecture_generated",
        )
        db.add(journey)
        db.commit()

        kp = KnowledgeProfile(
            journey_id=journey.id,
            overall_confidence="intermediate",
            summary="Learner knows basic arrays but needs stack invariants.",
            gaps=json.dumps(["LIFO Invariant"]),
            misconceptions=json.dumps([]),
        )
        db.add(kp)

        arch = NoteArchitecture(
            journey_id=journey.id,
            topic="Stack in DSA",
            learning_goal="Master Stack operations in C++",
            summary_rationale="Personalized for C++ learner.",
        )
        db.add(arch)
        db.flush()

        sec = NoteArchitectureSection(
            architecture_id=arch.id,
            order_index=1,
            title="Core Stack Mechanics",
            section_type="code_walkthrough",
            depth="standard",
            target_concepts=json.dumps(["Stack"]),
            rationale="Practical C++ implementation",
            needs_code=True,
            needs_visual=False,
        )
        db.add(sec)
        db.commit()

        mock_provider = MockLLMProvider(
            response_text=json.dumps({
                "blocks": [
                    {
                        "type": "code",
                        "language": "cpp",
                        "title": "C++ Stack Implementation",
                        "code": "#include <vector>\nclass Stack { std::vector<int> data; };",
                    }
                ]
            })
        )

        settings = get_settings()

        with patch("backend.app.note.generator.get_llm_provider", return_value=mock_provider):
            note_res = await generate_structured_note(
                journey_id=journey.id,
                db=db,
                settings=settings,
                user_id=user.id,
            )

        assert note_res.status_code if hasattr(note_res, "status_code") else True
        assert len(note_res.sections) == 1
        assert note_res.sections[0].blocks[0].language == "cpp"

        # Verify prompt instructed C++
        last_prompt = mock_provider.last_prompt
        assert "- Preferred Programming Language: cpp" in last_prompt
        assert "write all code implementations in cpp" in last_prompt
        assert '"language": "cpp"' in last_prompt
    finally:
        db.close()


def test_generate_note_endpoint_with_auth_header(client):
    import uuid
    from backend.app.models.user import User
    from backend.app.models.user_profile import UserProfile
    from backend.app.models.journey import LearningJourney
    from backend.app.core.security import create_access_token
    from backend.app.db.session import SessionLocal

    db = SessionLocal()
    try:
        user = User(
            email=f"auth_note_{uuid.uuid4().hex[:8]}@example.com",
            hashed_password="pw",
        )
        db.add(user)
        db.commit()

        up = UserProfile(
            user_id=user.id,
            experience_level="intermediate",
            preferred_language="cpp",
        )
        db.add(up)

        journey = LearningJourney(
            user_id=user.id,
            topic="Stack in DSA",
            status="created",
        )
        db.add(journey)
        db.commit()
        journey_id = journey.id
        token = create_access_token(user.id)
    finally:
        db.close()

    headers = {"Authorization": f"Bearer {token}"}

    # Step through pipeline
    client.post(f"/journeys/{journey_id}/discovery/start", headers=headers)
    client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "I know arrays well in C++"},
        headers=headers,
    )
    client.post(f"/journeys/{journey_id}/knowledge-profile", headers=headers)
    client.post(f"/journeys/{journey_id}/architecture", headers=headers)

    # Generate note with auth
    res = client.post(f"/journeys/{journey_id}/generate-note", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["journey_id"] == journey_id
    assert len(data["sections"]) >= 1



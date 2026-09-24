import pytest
from datetime import datetime, timezone
from pathlib import Path
from fastapi.testclient import TestClient

from backend.app.schemas.note import NoteResponse, NoteSectionData, NoteBlock
from backend.app.note.pdf import generate_note_pdf, clean_markdown_for_paragraph, wrap_preformatted


def create_sample_journey_for_pdf(client: TestClient) -> dict:
    """Helper to spin up a journey with profile, architecture, and living note."""
    j_res = client.post("/journeys", json={"topic": "Vector Search & HNSW Indexing"})
    assert j_res.status_code == 201
    journey = j_res.json()
    journey_id = journey["id"]

    # Start discovery
    d_start = client.post(f"/journeys/{journey_id}/discovery/start")
    assert d_start.status_code == 200

    # Answer probe
    d_ans = client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "I know basic cosine similarity, but HNSW graphs and quantization are gaps."},
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


def test_clean_markdown_for_paragraph():
    raw = "Special <tags> & ampersands with **bold** and *italic* and `code_snippet`."
    cleaned = clean_markdown_for_paragraph(raw)
    assert "&lt;tags&gt;" in cleaned
    assert "&amp;" in cleaned
    assert "<b>bold</b>" in cleaned
    assert "<i>italic</i>" in cleaned
    assert "Courier-Bold" in cleaned


def test_wrap_preformatted():
    long_line = "x" * 150
    wrapped = wrap_preformatted(long_line, max_chars=70)
    lines = wrapped.splitlines()
    assert len(lines) == 3
    assert len(lines[0]) == 70
    assert len(lines[1]) == 70
    assert len(lines[2]) == 10


def test_generate_note_pdf_binary_with_all_block_types():
    sample_note = NoteResponse(
        id="note-sample-pdf",
        journey_id="journey-sample-pdf",
        topic="Vector Search & HNSW Indexing",
        summary="A comprehensive technical guide to high-dimensional nearest neighbor indexing.",
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        revisions=[],
        sections=[
            NoteSectionData(
                id="sec-1",
                order_index=1,
                title="Graph-Based Index Foundations",
                section_type="foundational",
                depth="deep",
                blocks=[
                    NoteBlock(
                        type="paragraph",
                        content="High-dimensional vector search requires navigating spatial embeddings efficiently.",
                    ),
                    NoteBlock(
                        type="definition",
                        term="HNSW Multi-Layer Graph",
                        content="Hierarchical Navigable Small World uses skip-list inspired layer hierarchies.",
                    ),
                    NoteBlock(
                        type="warning",
                        title="Memory Pressure",
                        content="HNSW stores edge lists in RAM, requiring significant memory overhead.",
                    ),
                    NoteBlock(
                        type="example",
                        title="Cosine Distance Calculation",
                        content="Dot product normalized by vector Euclidean norms.",
                    ),
                    NoteBlock(
                        type="code",
                        language="python",
                        title="Euclidean Distance Kernel",
                        code="import numpy as np\n\ndef l2_dist(a, b):\n    return np.linalg.norm(a - b)",
                        complexity="Time: O(D) | Space: O(1)",
                        expected_output="0.1428",
                    ),
                    NoteBlock(
                        type="diagram",
                        title="Layered Graph Traversal",
                        diagram_type="flowchart",
                        visual_description="Top layer entry point beams down through densifying graph layers.",
                        diagram_spec="graph TD\n  TopLayer --> MidLayer\n  MidLayer --> BottomLayer",
                        caption="HNSW Beam Search Progression",
                    ),
                    NoteBlock(
                        type="comparison",
                        title="Index Algorithm Tradeoffs",
                        content="Evaluating index performance across key dimensions:",
                        items=[
                            {"Algorithm": "Flat L2", "Recall": "100%", "Query Latency": "High", "Build Time": "0s"},
                            {"Algorithm": "HNSW", "Recall": "98%", "Query Latency": "Ultra-Low", "Build Time": "Minutes"},
                            {"Algorithm": "IVF-PQ", "Recall": "90%", "Query Latency": "Low", "Build Time": "Moderate"},
                        ],
                    ),
                ],
            )
        ],
    )

    pdf_bytes = generate_note_pdf(sample_note)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF-")


def test_generate_note_pdf_handles_edge_cases_and_missing_fields():
    edge_note = NoteResponse(
        id="note-edge",
        journey_id="journey-edge",
        topic="Edge Cases: Special <Chars> & Quotes \"Test\"",
        summary="Testing edge cases with None fields and empty block attributes.",
        version=3,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        revisions=[],
        sections=[
            NoteSectionData(
                id="sec-edge-1",
                order_index=1,
                title="Special & Characters <Section>",
                section_type="edge_test",
                depth="intermediate",
                blocks=[
                    NoteBlock(type="paragraph", content=None),
                    NoteBlock(type="definition", term=None, content="Definition with missing term"),
                    NoteBlock(type="warning", title=None, content=None),
                    NoteBlock(type="example", title=None, content="Example text"),
                    NoteBlock(type="code", language=None, title=None, code=None, content="print('fallback content')"),
                    NoteBlock(type="diagram", title=None, diagram_spec=None, content="graph LR; A-->B;"),
                    NoteBlock(type="comparison", title=None, content=None, items=None),
                ],
            )
        ],
    )

    pdf_bytes = generate_note_pdf(edge_note)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")


def test_export_note_by_id_pdf_endpoint(client: TestClient):
    data = create_sample_journey_for_pdf(client)
    note_id = data["note"]["id"]

    res = client.get(f"/notes/{note_id}/export?format=pdf")
    assert res.status_code == 200
    assert "application/pdf" in res.headers.get("content-type", "")
    assert "attachment" in res.headers.get("content-disposition", "")
    assert ".pdf" in res.headers.get("content-disposition", "")
    assert res.content.startswith(b"%PDF-")


def test_export_note_by_id_direct_pdf_endpoint(client: TestClient):
    data = create_sample_journey_for_pdf(client)
    note_id = data["note"]["id"]

    res = client.get(f"/notes/{note_id}/export/pdf")
    assert res.status_code == 200
    assert "application/pdf" in res.headers.get("content-type", "")
    assert res.content.startswith(b"%PDF-")


def test_export_note_by_journey_pdf_endpoint(client: TestClient):
    data = create_sample_journey_for_pdf(client)
    journey_id = data["journey_id"]

    # Query param format=pdf
    res1 = client.get(f"/journeys/{journey_id}/note/export?format=pdf")
    assert res1.status_code == 200
    assert "application/pdf" in res1.headers.get("content-type", "")
    assert res1.content.startswith(b"%PDF-")

    # Direct /pdf path
    res2 = client.get(f"/journeys/{journey_id}/note/export/pdf")
    assert res2.status_code == 200
    assert "application/pdf" in res2.headers.get("content-type", "")
    assert res2.content.startswith(b"%PDF-")


def test_export_pdf_not_found(client: TestClient):
    res1 = client.get("/notes/non-existent-note-id/export?format=pdf")
    assert res1.status_code == 404

    res2 = client.get("/journeys/non-existent-journey-id/note/export/pdf")
    assert res2.status_code == 404


def test_frontend_has_export_pdf_button():
    index_html_path = Path("frontend/index.html")
    assert index_html_path.exists()
    content = index_html_path.read_text(encoding="utf-8")

    assert 'id="btn-export-pdf"' in content
    assert "exportNote('pdf')" in content
    assert "Export PDF" in content

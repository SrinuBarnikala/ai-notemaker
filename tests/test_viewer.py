import pytest
from starlette.testclient import TestClient
from backend.app.main import app




def test_viewer_html_contains_reader_components(client):
    """Verify that index.html contains the necessary components for the Web Note Viewer."""
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    
    # Check for Phase 6 elements
    assert "PHASE 6" in html
    assert "reading-progress-bar" in html
    assert "note-toc" in html or "note-viewer-toc" in html
    assert "note-reader-controls" in html or "reader-toolbar" in html
    assert "copyCode" in html or "copy-btn" in html


def test_note_viewer_data_integrity(client):
    """Verify that the note payload provides all metadata needed for the reader: word count, sections, blocks, etc."""
    # 1. Create a journey
    res = client.post("/journeys", json={"topic": "Docker Container Internals"})
    assert res.status_code == 201
    journey_id = res.json()["id"]

    # 2. Advance through discovery, profile, architecture, note
    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "I know basic docker run, but want to understand cgroups and namespaces."})
    client.post(f"/journeys/{journey_id}/knowledge-profile")
    client.post(f"/journeys/{journey_id}/architecture")
    note_res = client.post(f"/journeys/{journey_id}/generate-note")
    assert note_res.status_code == 200
    note_data = note_res.json()

    # 3. Retrieve note directly for viewer
    get_res = client.get(f"/journeys/{journey_id}/note")
    assert get_res.status_code == 200
    viewer_data = get_res.json()

    assert viewer_data["id"] == note_data["id"]
    assert viewer_data["journey_id"] == journey_id
    assert viewer_data["topic"] == "Docker Container Internals"
    assert viewer_data["version"] >= 1
    assert len(viewer_data["sections"]) > 0

    # Ensure every section has order_index, title, depth, and blocks
    for sec in viewer_data["sections"]:
        assert sec["order_index"] >= 1
        assert len(sec["title"]) > 0
        assert sec["depth"] in ["brief", "standard", "deep"]
        assert len(sec["blocks"]) > 0

        # Validate that block types are valid
        for block in sec["blocks"]:
            assert block["type"] in [
                "paragraph", "definition", "example", "code", "warning", "comparison", "diagram"
            ]


def test_note_viewer_retrieval_by_note_id(client):
    """Verify that viewer can load directly via /notes/{note_id}."""
    # Create and generate note
    res = client.post("/journeys", json={"topic": "PostgreSQL Indexing B-Trees"})
    journey_id = res.json()["id"]
    client.post(f"/journeys/{journey_id}/discovery/start")
    client.post(f"/journeys/{journey_id}/discovery/answer", json={"answer": "I understand B-trees theoretically."})
    client.post(f"/journeys/{journey_id}/knowledge-profile")
    client.post(f"/journeys/{journey_id}/architecture")
    note = client.post(f"/journeys/{journey_id}/generate-note").json()

    # Direct fetch by note_id
    note_id = note["id"]
    direct_res = client.get(f"/notes/{note_id}")
    assert direct_res.status_code == 200
    assert direct_res.json()["id"] == note_id


def test_modal_escape_handling_and_components(client):
    """Verify that all modals/drawers exist in index.html and app.js handles Escape dismiss."""
    root_res = client.get("/")
    assert root_res.status_code == 200
    html = root_res.text

    # Modal elements in DOM
    expected_modal_ids = [
        "copilot-drawer",
        "spotlight-search-modal",
        "version-history-modal",
        "knowledge-memory-modal",
        "concept-provenance-modal",
        "assessment-modal",
        "evolve-modal",
        "diag-fullscreen-modal",
        "section-visual-modal",
        "section-code-modal",
    ]
    for m_id in expected_modal_ids:
        assert m_id in html, f"Expected modal #{m_id} to be present in index.html"

    # Verify app.js contains all Escape handlers
    from pathlib import Path
    app_js_path = Path("frontend/js/app.js")
    assert app_js_path.exists()
    app_js_content = app_js_path.read_text(encoding="utf-8")

    assert "Escape" in app_js_content
    close_handlers = [
        "closeCopilotDrawer",
        "closeSearchModal",
        "closeVersionHistoryModal",
        "closeMemoryModal",
        "closeConceptProvenanceModal",
        "closeAssessmentModal",
        "closeEvolveModal",
        "closeDiagramModal",
        "closeSectionVisualModal",
        "closeSectionCodeModal",
        "closeGraphModal",
        "closeConceptInspector",
    ]
    for handler in close_handlers:
        assert handler in app_js_content, f"Expected handler {handler} in app.js Escape listener"

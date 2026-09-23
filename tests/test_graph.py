import pytest
from fastapi.testclient import TestClient


def create_sample_journey_for_graph(client: TestClient) -> dict:
    """Helper to spin up a journey with profile and note for graph tests."""
    j_res = client.post("/journeys", json={"topic": "Linux eBPF & Kernel Tracing"})
    assert j_res.status_code == 201
    journey = j_res.json()
    journey_id = journey["id"]

    # Start discovery
    d_start = client.post(f"/journeys/{journey_id}/discovery/start")
    assert d_start.status_code == 200

    # Answer probe
    d_ans = client.post(
        f"/journeys/{journey_id}/discovery/answer",
        json={"answer": "I know basic user space tracing, but eBPF verifier and BPF maps are gaps."},
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

    return {
        "journey_id": journey_id,
        "note": n_res.json(),
    }


def test_journey_graph_generation_flow(client: TestClient):
    data = create_sample_journey_for_graph(client)
    journey_id = data["journey_id"]

    res = client.get(f"/journeys/{journey_id}/graph")
    assert res.status_code == 200
    payload = res.json()

    assert payload["journey_id"] == journey_id
    assert payload["is_global"] is False
    assert payload["total_nodes"] >= 2
    assert len(payload["nodes"]) == payload["total_nodes"]
    assert payload["total_edges"] >= 1
    assert len(payload["edges"]) == payload["total_edges"]
    assert "mastery_breakdown" in payload
    assert isinstance(payload["mastery_breakdown"], dict)

    # Validate node fields
    node_ids = {n["id"] for n in payload["nodes"]}
    for n in payload["nodes"]:
        assert n["name"]
        assert n["status"] in ["known", "partial", "gap", "misconception"]
        assert n["size"] >= 15

    # Validate edge source and target connectivity
    for e in payload["edges"]:
        assert e["source"] in node_ids
        assert e["target"] in node_ids
        assert e["relationship"] in ["prerequisite", "subconcept", "compares_to", "implements", "relates_to"]


def test_global_graph_flow(client: TestClient):
    create_sample_journey_for_graph(client)

    res = client.get("/graph/global")
    assert res.status_code == 200
    payload = res.json()

    assert payload["is_global"] is True
    assert payload["total_nodes"] >= 1
    assert len(payload["nodes"]) == payload["total_nodes"]
    assert "mastery_breakdown" in payload


def test_graph_error_handling(client: TestClient):
    res = client.get("/journeys/nonexistent-journey-9999/graph")
    assert res.status_code == 404


def test_graph_frontend_elements_present(client: TestClient):
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    assert "graph-modal" in html
    assert "graph-canvas" in html
    assert "graph.js" in html

    # Phase 12 Refinement: Learning UX & Concept Inspector Elements
    assert "graph-body-layout" in html
    assert "graph-inspector-panel" in html
    assert "graph-path-banner" in html
    assert "btn-graph-scope-neighbor" in html
    assert "btn-graph-scope-all" in html
    assert "btn-graph-learning-path" in html

    # Inspector details & action buttons
    assert "inspector-concept-title" in html
    assert "inspector-recommendation-box" in html
    assert "inspector-prereqs-list" in html
    assert "inspector-unlocks-list" in html
    assert "btn-graph-goto-note" in html
    assert "btn-graph-ask-copilot" in html
    assert "btn-graph-trace-path" in html
    assert "edge-legend-line" in html

    # In-App Fullscreen Workspace Controls
    assert "btn-graph-fullscreen" in html
    assert "graph-fullscreen-icon" in html
    assert "graph-fullscreen-label" in html
    assert "graph-workspace-badge" in html

    # Phase 12 Final Refinement: Explore Knowledge Elements
    assert "btn-graph-mode-global" in html
    assert "Explore Knowledge" in html
    assert "graph-explore-hud" in html
    assert "graph-subgraph-hud" in html
    assert "graph-search-dropdown" in html
    assert "btn-explore-reset-hub" in html




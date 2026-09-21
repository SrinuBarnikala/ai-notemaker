def test_create_journey_success(client):
    payload = {"topic": "How does RAG work internally?"}
    response = client.post("/journeys", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert len(data["id"]) > 0
    assert data["topic"] == "How does RAG work internally?"
    assert data["status"] == "created"
    assert "created_at" in data
    assert "updated_at" in data


def test_create_journey_whitespace_trimmed(client):
    payload = {"topic": "   Vector Databases & Reranking   "}
    response = client.post("/journeys", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["topic"] == "Vector Databases & Reranking"


def test_create_journey_empty_topic_rejected(client):
    payload = {"topic": "    "}
    response = client.post("/journeys", json=payload)
    assert response.status_code == 422


def test_create_journey_too_short_rejected(client):
    payload = {"topic": "x"}
    response = client.post("/journeys", json=payload)
    assert response.status_code == 422


def test_get_journey_by_id(client):
    # First create
    create_resp = client.post("/journeys", json={"topic": "Transformer Self-Attention"})
    assert create_resp.status_code == 201
    journey_id = create_resp.json()["id"]

    # Now retrieve
    get_resp = client.get(f"/journeys/{journey_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["id"] == journey_id
    assert data["topic"] == "Transformer Self-Attention"
    assert data["status"] == "created"


def test_get_journey_not_found(client):
    response = client.get("/journeys/non-existent-id-999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_list_journeys(client):
    # Ensure at least 2 exist
    client.post("/journeys", json={"topic": "Distributed Raft Consensus"})
    client.post("/journeys", json={"topic": "FastAPI Dependency Injection"})

    response = client.get("/journeys")
    assert response.status_code == 200
    data = response.json()
    assert "journeys" in data
    assert "total" in data
    assert data["total"] >= 2
    assert len(data["journeys"]) >= 2

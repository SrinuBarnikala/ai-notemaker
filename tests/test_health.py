def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "version" in data
    assert "database" in data
    assert data["llm_provider"] == "mock"
    assert data["llm_model"] == "mock-qwen"
    assert "llm_healthy" in data
    assert data["model_available"] is True
    assert data["model_warning"] is None


def test_root_serves_frontend(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Personalized Technical Note Maker" in response.text
    assert "llm-status-badge" in response.text

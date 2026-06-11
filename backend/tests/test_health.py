"""
Tests for health check and root endpoints.
"""


class TestRootEndpoints:
    def test_home(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "2.1.0"
        assert "message" in data

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")
        assert "mongodb" in data
        assert "redis" in data
        assert "disk" in data
        assert "ml_classifier" in data

    def test_collect_telemetry(self, client):
        response = client.post("/collect")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

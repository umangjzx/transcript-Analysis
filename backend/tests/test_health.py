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

    def test_health_unauthenticated(self, client):
        """Unauthenticated /health returns minimal status (no topology leak)."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")
        assert data["service"] == "Audio Safety Analyzer"
        assert data["version"] == "2.1.0"
        # Should NOT expose internal topology without auth
        assert "redis" not in data
        assert "ollama" not in data

    def test_health_authenticated(self, client, auth_headers):
        """Authenticated /health returns full service topology."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")
        # Authenticated response includes topology details
        assert "ml_classifier" in data
        assert "disk" in data

    def test_collect_telemetry(self, client):
        response = client.post("/collect")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

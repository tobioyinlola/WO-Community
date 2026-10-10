import pytest
from django.db import connection

pytestmark = pytest.mark.django_db


def test_liveness(api_client):
    response = api_client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_ok_when_dependencies_reachable(api_client):
    assert api_client.get("/health/ready").status_code == 200


def test_readiness_reports_unavailable_when_database_fails(api_client, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(connection, "cursor", broken)
    response = api_client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_ping_is_public(api_client):
    response = api_client.get("/api/v1/ping")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_schema_is_served_and_documents_routes(api_client):
    response = api_client.get("/api/v1/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/me" in paths
    assert "/api/v1/ping" in paths

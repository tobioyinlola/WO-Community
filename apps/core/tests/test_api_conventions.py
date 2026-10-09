import pytest

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("policy_urls")]


def test_validation_errors_use_problem_details(make_user, client_for):
    response = client_for(make_user()).post("/echo", {"name": "x" * 50})
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["status"] == 400
    assert "name" in body["errors"]
    assert response["Content-Type"] == "application/problem+json"


def test_unknown_fields_are_rejected(make_user, client_for):
    response = client_for(make_user()).post("/echo", {"name": "ok", "role": "super_admin"})
    assert response.status_code == 400
    assert response.json()["errors"] == {"role": "Unknown field."}


def test_valid_payload_passes(make_user, client_for):
    response = client_for(make_user()).post("/echo", {"name": "ok"})
    assert response.status_code == 200
    assert response.json() == {"name": "ok"}


def test_malformed_json_is_a_client_error(make_user, client_for):
    response = client_for(make_user()).post("/echo", "{not json", content_type="application/json")
    assert response.status_code == 400
    assert response.json()["code"] == "malformed_request"


def test_unhandled_errors_do_not_leak_internals(api_client):
    api_client.raise_request_exception = False
    response = api_client.get("/boom")
    assert response.status_code == 500
    assert "secret internal detail" not in response.content.decode()
    assert response.json()["code"] == "server_error"


def test_unknown_route_is_not_found_problem_free_of_internals(api_client):
    response = api_client.get("/does-not-exist")
    assert response.status_code == 404


def test_responses_carry_request_id_and_security_headers(api_client):
    response = api_client.get("/public", HTTP_X_REQUEST_ID="abcdef123456")
    assert response["X-Request-ID"] == "abcdef123456"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["X-Frame-Options"] == "DENY"
    assert response["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "frame-ancestors 'none'" in response["Content-Security-Policy"]
    assert response["Permissions-Policy"]
    assert response["Cross-Origin-Resource-Policy"] == "same-site"


def test_hostile_request_id_is_replaced(api_client):
    response = api_client.get("/public", HTTP_X_REQUEST_ID="bad id\r\nSet-Cookie: x=1")
    assert response["X-Request-ID"] != "bad id"
    assert "Set-Cookie" not in response

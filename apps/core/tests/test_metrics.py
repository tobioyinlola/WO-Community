import pytest

pytestmark = pytest.mark.django_db


def test_metrics_do_not_exist_until_a_token_is_set(api_client):
    assert api_client.get("/metrics").status_code == 404


def test_metrics_need_the_bearer_token(api_client, settings):
    settings.METRICS_TOKEN = "scrape-secret"
    assert api_client.get("/metrics").status_code == 401
    assert api_client.get("/metrics", HTTP_AUTHORIZATION="Bearer wrong").status_code == 401


def test_metrics_report_requests_and_queues(api_client, settings):
    settings.METRICS_TOKEN = "scrape-secret"
    api_client.get("/api/v1/ping")
    response = api_client.get("/metrics", HTTP_AUTHORIZATION="Bearer scrape-secret")
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    body = response.content.decode()
    assert "wo_http_requests_total" in body and 'route="api/v1/ping"' in body
    assert "wo_outbox_pending" in body and "wo_outbox_oldest_pending_seconds" in body
    assert "wo_failed_tasks" in body
    assert 'route="metrics"' not in body  # scraping does not count itself


def test_tracing_is_off_without_a_collector(settings):
    from config import telemetry

    settings.OTEL_EXPORTER_OTLP_ENDPOINT = ""
    assert telemetry.setup("test") is False


def test_trace_spans_never_carry_query_strings():
    from config import telemetry

    class Span:
        attributes: dict = {}

        def is_recording(self):
            return True

        def set_attribute(self, key, value):
            self.attributes[key] = value

    class Request:
        path = "/api/v1/verify"

        def build_absolute_uri(self, path):
            return f"https://api.example.com{path}"

    span = Span()
    telemetry._redact(span, Request())
    assert span.attributes["url.query"] == ""
    assert span.attributes["http.url"] == "https://api.example.com/api/v1/verify"

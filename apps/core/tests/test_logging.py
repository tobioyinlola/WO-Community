from apps.core.logging import REDACTED, redact


def test_sensitive_keys_are_redacted_at_any_depth():
    cleaned = redact(
        {
            "event": "login",
            "password": "hunter2",
            "headers": {"Authorization": "Bearer abc", "Accept": "json"},
            "items": [{"refresh_token": "r"}],
            "user_id": "u1",
        }
    )
    assert cleaned["password"] == REDACTED
    assert cleaned["headers"]["Authorization"] == REDACTED
    assert cleaned["headers"]["Accept"] == "json"
    assert cleaned["items"][0]["refresh_token"] == REDACTED
    assert cleaned["user_id"] == "u1"

PASSWORD = "a-long-test-passphrase"
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}

REGISTER_URL = "/api/v1/auth/register"
VERIFY_URL = "/api/v1/auth/verify-email"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
FORGOT_URL = "/api/v1/auth/password/forgot"
RESET_URL = "/api/v1/auth/password/reset"


def registration_payload(**overrides):
    payload = {
        "email": "new.member@example.com",
        "password": PASSWORD,
        "accepted_terms": True,
        "accepted_privacy": True,
        "accepted_conduct": True,
    }
    payload.update(overrides)
    return payload

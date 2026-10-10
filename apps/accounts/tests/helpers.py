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
        "profile": {"full_name": "Ada Founder", "country": "NG", "city": "Lagos"},
        "startup": {
            "name": "Ada Pay",
            "country": "NG",
            "city": "Lagos",
            "sector": "fintech",
            "stage": "seed",
            "pitch": "Payments for small traders",
        },
    }
    payload.update(overrides)
    return payload


MFA_VERIFY_URL = "/api/v1/auth/mfa/verify"
MFA_ENROL_URL = "/api/v1/auth/mfa/enrol"
MFA_CONFIRM_URL = "/api/v1/auth/mfa/confirm"
MFA_STEP_UP_URL = "/api/v1/auth/mfa/step-up"
MFA_RECOVERY_URL = "/api/v1/auth/mfa/recovery-codes"


def totp_code(secret: str, offset: int = 0) -> str:
    """The authenticator code for the current 30 second step, or a neighbouring one."""
    import time

    import pyotp

    return pyotp.TOTP(secret).at(int(time.time()) + offset * 30)

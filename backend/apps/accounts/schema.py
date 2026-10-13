from drf_spectacular.extensions import OpenApiAuthenticationExtension


class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.JWTAuthentication"
    name = "bearerAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}


class OptionalJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """The same bearer token, but a call without one (or with a bad one) is still allowed."""

    target_class = "apps.accounts.authentication.OptionalJWTAuthentication"
    name = "optionalBearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Optional: send it when signed in so events are tied to the member.",
        }
